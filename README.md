This demo shows different stages of an app: running locally, deployed
to PCF Dev and finally deployed to the full-blown PCF.

Questions? Contact [Beibei.Yang@dell.com](Beibei.Yang@dell.com)

# Run Locally

Install Python 2.7 or Anaconda Python 2.x (Anaconda recommended): https://www.continuum.io/downloads

Install virtualenv: https://pypi.python.org/pypi/virtualenv

Install Redis: https://redis.io/download

cd to the app1_local directory

Run:
```
pip install -r requirements.txt
```

Launch either app1 or app2:

```
bokeh serve --port=8080 --address=localhost --show app
```

This will launch the app in your default browser.

# PCF Dev

See app1_pcfdev and app2_pcfdev directories.

Login via CF-CLI and create a Redis Service
```shell
cf login -a https://api.local.pcfdev.io
cf marketplace
cf create-service p-redis shared-vm iot_redis
```

Modify `manifest.yml` to point to the new redis service `iot_redis`. Update MongoDB credentials.

Modify `Procfile` as needed. Note that `--allow-websocket-origin` must point to the full URL of the app to be deployed.

```shell
--allow-websocket-origin=iotapp1.local.pcfdev.io
```

Push to PCF Dev:
```shell
cf push
```

# Pivotal Web Services (or Pivotal Cloud Foundry)

See app1_pcf and app2_pcf directories. Note that Procfile for Pivotal Web Services looks different compared to PCF Dev. This is
because Pivotal Web Services limits websocket to be secured and only at the non-standard port 4443.

Login via CF-CLI and create a Redis Service
```shell
cf login -a api.run.pivotal.io
cf marketplace
cf create-service rediscloud 30mb iot_redis
```

Modify `manifest.yml` to point to the new redis service `iot_redis`. Update MongoDB credentials.

Modify `Procfile`. Note that you must point `--allow-websocket-origin` to the full URL of the app to be deployed.
For Pivotal Web Services, you must provide the websocket port 4443. For Pivotal Cloud Foundry, you can ignore
the websocket port and it will pick up the default port 443.

```shell
--allow-websocket-origin=iotapp1.cfapps.io:4443
```

Push to PCF Dev:
```shell
cf push
```
