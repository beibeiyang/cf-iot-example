from pymongo import MongoClient, errors
import os, sys
import json
import redis
import time, datetime
import calendar
import numpy as np
from bokeh.layouts import layout, widgetbox
from bokeh.models.widgets import Select, Slider, Div, Button, Panel, Tabs, CheckboxGroup
from bokeh.models.widgets import DataTable, TableColumn
from bokeh.models import ColumnDataSource, HoverTool
from bokeh.io import curdoc
from bokeh.plotting import figure

mongoip = "mongo.your-domain.com"
mongouser = "mongouser"
mongopwd = "mongopassword"
mongoauthsrc = "mongodbname"
mongoport = 27017

mongoip = os.getenv('MONGO_ENV_SERVER_IP', mongoip)
mongouser = os.getenv('MONGO_ENV_USERNAME', mongouser)
mongopwd = os.getenv('MONGO_ENV_PASSWORD', mongopwd)
mongoauthsrc = os.getenv('MONGO_ENV_AUTHSOURCE', mongoauthsrc)
mongoport = int(os.getenv('MONGO_ENV_PORT', mongoport))

uri = "mongodb://{}:{}@{}:{}/?authSource={}".format(mongouser, mongopwd, mongoip, mongoport, mongoauthsrc)

print ("url:", uri)

try:
    db = MongoClient(uri).get_database(mongoauthsrc)
except errors.ConnectionFailure as e:
    print ("Could not connect to server: %s" % e)
    sys.exit(-1)

# Get Redis credentials
if 'VCAP_SERVICES' in os.environ:
    services = json.loads(os.getenv("VCAP_SERVICES"))
    # PCFDev uses 'p-redis' and PCf uses 'rediscloud' as servicename
    servicename, servicedetail = services.popitem()
    redis_env = servicedetail[0]["credentials"]
else:
    redis_env = dict(host="localhost", port=6379, password="")

# RedisCloud service uses key "hostname" instead of key "host" in p-redis
if "hostname" in redis_env:
    redis_env["host"] = redis_env["hostname"]
    del redis_env["hostname"]

redis_env["port"] = int(redis_env["port"])

# Connect to redis
try:
    redisconn = redis.StrictRedis(**redis_env)
    #print(r.info())
except redis.ConnectionError as e:
    print ("Redis error: %s" % e)
    sys.exit(-1)

redisconn.flushall()

notificationDiv = Div(text="", width=800)

gateways = []
if redisconn.get("gateways"):
    gateways = json.loads(redisconn.get("gateways"))
else:
    try:
        cursor = db.gateways.find( {}, {"id":1, "name":1} )
        gateways = []
        gateways.append((None, "--- Choose a Gateway ---"))
        for d in cursor:
            gateways.append((d["id"], d["name"]))
        redisconn.set("gateways", json.dumps(gateways))
    except errors.ServerSelectionTimeoutError as e:
        print ("MongoDB Server timed out: %s" % e)
        notificationDiv.text = "MongoDB Server timed out: %s" % e
        sys.exit(-1)

gatewayControl = Select( title="Choose a Gateway", options=gateways)
deviceControl = Select( title="Choose a Device")
indicatorControl = Select( title="Choose an indicator")
submitButton = Button(label="Submit", button_type="primary")
timemachine = Slider(title="How many minutes back would you like to travel", start=1, end=30, value=1, step=1,
                     callback_policy="mouseup")
controls = [gatewayControl, deviceControl, indicatorControl, timemachine, submitButton, notificationDiv]

doc = curdoc()
source = ColumnDataSource(data=dict(last_mod_date=[None], date=[None], v=[None]))
# source = ColumnDataSource(data=dict(last_mod_date=[None], date=[None], v=[None]))

# hover = HoverTool(tooltips=[
#     ("Date", "@s"),
#     (indicatorControl.value, "@v")
# ])

p = figure(title="", x_axis_type="datetime", plot_width=600, plot_height=400)
p.line('last_mod_date', "v", source=source)
tab1 = Panel(child=p, title="Plot")

columns = [
    TableColumn(field="last_mod_date", title="TimeStamp"),
    TableColumn(field="date", title="Date"),
    TableColumn(field="v", title="Value"),
]
dataTable = DataTable(source=source, columns=columns, width=800, height=600)

tab2 = Panel(child=dataTable, title="Table")
tabs = Tabs(tabs=[tab1, tab2 ])

# tabs.css_classes = ["hide"]

autoUpdateCheckbox = CheckboxGroup(
    labels=["Auto Update Data Source (every 15s)"], active=[])
autoUpdateCheckbox.disabled = True

gatewayControl.on_change('value', lambda attr, old, new: update_device())
deviceControl.on_change('value', lambda attr, old, new: update_indicator())
submitButton.on_click(lambda: callback())
autoUpdateCheckbox.on_click(lambda attr: auto_update(attr))

sizing_mode = 'fixed'  # 'scale_width' also looks nice with this example
inputs = widgetbox(*controls, sizing_mode=sizing_mode, name="widgets")
plotwidget = widgetbox([autoUpdateCheckbox, tabs], sizing_mode=sizing_mode, name="plotwidget")

mainLayout = layout(children=[
    [inputs, plotwidget]
], sizing_mode=sizing_mode, name="mainLayout")

doc.add_root(mainLayout)
doc.title = "ACME IoT Analytics"

def epoch_to_datetime(epoch):
    """
    :param epoch: str of epoch time
    :return: converted datetime type
    """
    return datetime.datetime.fromtimestamp(float(epoch) / 1000)


def callback(mainLayout=mainLayout, source=source):
    fig = mainLayout.children[0].children[1].children[1].tabs[0].child
    autoUpdateCheckbox.disabled = False

    if not deviceControl.value or not indicatorControl.value:
        return

    dsIdNames = {}
    for d in db.datasets.find({"device_id": deviceControl.value}):
        dsIdNames[d["id"]] = d["name"]

    print ("dsIdNames: %s" % dsIdNames)

    currTs = calendar.timegm(time.gmtime())*1000   # current epoch time in miliseconds
    oldestTs = currTs - timemachine.value * 60 * 1000
    print("Current timestamp: %s \t, Oldest timestamp: %s", currTs, oldestTs)

    print ("mainLayout.children: %s" % mainLayout.children)

    n = 0
    for id in dsIdNames:
        dates = []
        vs = []
        print("dataset_id: %s" % id)
        print("oldestTs: %s" % oldestTs)

        # expensive call
        cursor = db.dataitems.find({"dataset_id": id, "last_mod_date": {"$gt": oldestTs} })
        count = cursor.count()
        print("Visit the past %s min" % timemachine.value)
        print("Retrieving %s document(s)" % count)

        # if a device corresponds to multiple datasets and
        # the later dataset is empty, skip and do not update
        # the notificationDiv
        if n > 0 and count==0:
            continue

        notificationDiv.text = "Found {} record".format(count)
        if count > 1:
            notificationDiv.text += "s"

        if count == 0:
            continue

        n = n + count

        for d in cursor:
            if indicatorControl.value not in d["v"]:
                continue
            date = d["last_mod_date"]
            v = d["v"][indicatorControl.value]
            if v is None:
                continue
            dates.append(epoch_to_datetime(date))
            vs.append(v)

        dates = np.array(dates, dtype='datetime64[ms]')
        source.data = dict(last_mod_date=dates, date=[str(d) for d in dates], v=vs)
        print("len(dsIdNames): %s" % len(dsIdNames))
        print("id: %s, dsIdNames[id]: %s" % (id, dsIdNames[id]))
        print("source.data: %s" % source.data)

        fig.title.text = dsIdNames[id]
        fig.grid.grid_line_alpha = 0.3
        fig.xaxis.axis_label = "DateTime"
        fig.yaxis.axis_label = indicatorControl.value

        if autoUpdateCheckbox.disabled:
            autoUpdateCheckbox.disabled = False

    # reset plot and table if no records
    if n == 0:
        source.data = dict(last_mod_date=[None], date=[None], v=[None])
        fig.title.text = ""
        fig.xaxis.axis_label = ""
        fig.yaxis.axis_label = ""


from threading import Timer
def auto_update(attr):
    print("attr: %s" % attr)
    if len(attr) > 0:
        # box checked
        Timer(15, auto_update, args=[attr]).start()     # run callback every 15 seconds
        # submitButton.trigger("clicks", None, None)
        doc.add_next_tick_callback(callback)
    else:
        return


def update_device():
    gatewayId = gatewayControl.value
    if not gatewayId:
        return
    # reset device and indicator dropdowns
    deviceControl.options = []
    indicatorControl.options = []
    rkey = "device&gatewayId=" + gatewayId
    if redisconn.get(rkey):
        deviceControl.options = json.loads(redisconn.get(rkey))
    else:
        deviceControl.options = []
        devices = list()
        devices.append((None, "--- Choose a Device ---"))
        for d in db.devices.find({ "parent_id": gatewayId }):
            devices.append((d["id"], d["name"]))
        deviceControl.options = devices
        redisconn.set(rkey, json.dumps(devices))
    doc.add_next_tick_callback(callback)


def update_indicator():
    deviceId = deviceControl.value
    if not deviceId:
        return
    # reset indicator dropdown
    indicatorControl.options = []
    rkey = "indicators&deviceId=" + deviceId
    if redisconn.get(rkey):
        indicatorControl.options = json.loads(redisconn.get(rkey))
    else:
        indicatorControl.options = list()
        device = db.devices.find_one({ "id": deviceId } )
        indicators = [(None, "--- Choose an indicator ---")]
        indicators = indicators + device["indicator_names"]
        indicatorControl.options = indicators
        redisconn.set(rkey, json.dumps(indicators))
    doc.add_next_tick_callback(callback)