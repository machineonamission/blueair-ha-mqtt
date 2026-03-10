import paho.mqtt.client as mqtt
import urllib.parse
import ssl
import json


# #               cn:  a2du5f95w7oz2a.ats.iot.cn-north-1.amazonaws.com.cn"
# #               us:    "a3tpdpjvxk6yog-ats.iot.us-east-2.amazonaws.com"
# #               other:  a3tpdpjvxk6yog-ats.iot.eu-west-1.amazonaws.com"
AWS_IOT_ENDPOINT = "a3tpdpjvxk6yog-ats.iot.us-east-2.amazonaws.com"

# TODO: rip code from blueair_api to get these automatically
TOKEN = ""
SIGNATURE = ""

# The exact Client ID verified by Frida
def on_log(client, userdata, level, buf):
    print(f"[LOG] {buf}")

def on_connect(client, userdata, flags, reason_code, properties):
    if reason_code == 0:
        print("\n[+] SUCCESS! WE ARE IN.")

        # Subscribe to the exact state topic
        topic_state = f"d/{DEVICE_ID}/s/5s"
        print(f"[*] Subscribing to: {topic_state}")
        client.subscribe(topic_state)

        # Subscribe to the AWS Device Shadow topic
        topic_shadow = f"$aws/things/{DEVICE_ID}/shadow/update/documents"
        print(f"[*] Subscribing to: {topic_shadow}")
        client.subscribe(topic_shadow)
    else:
        print(f"\n[-] Connection failed with code {reason_code}")

def on_message(client, userdata, msg):
    print(f"\n[<<< INCOMING MSG <<<] Topic: {msg.topic}")
    try:
        payload = json.loads(msg.payload.decode('utf-8'))
        print(json.dumps(payload, indent=2))
    except json.JSONDecodeError:
        print(msg.payload.decode('utf-8'))

# Setup the client
client = mqtt.Client(
    mqtt.CallbackAPIVersion.VERSION2,
    client_id=CLIENT_ID,
    transport="websockets",
    clean_session=True
)

client.on_log = on_log
client.on_connect = on_connect
client.on_message = on_message

# Set up TLS
ssl_context = ssl.create_default_context()
client.tls_set_context(ssl_context)

# ---------------------------------------------------------
# THE FIX: Pass the Custom Authorizer tokens as WSS Headers
# ---------------------------------------------------------
custom_headers = {
    "X-Amz-CustomAuthorizer-Name": "custom-authorizer",
    "X-Amz-CustomAuthorizer-Signature": SIGNATURE,
    "X-Amz-CustomAuthorizer-Token": TOKEN
}

# The path is just standard /mqtt now
client.ws_set_options(path="/mqtt", headers=custom_headers)

print("[*] Initiating connection...")
try:
    client.connect(AWS_IOT_ENDPOINT, 443, 60)
    client.loop_forever()
except KeyboardInterrupt:
    print("\n[*] Disconnecting...")
    client.disconnect()
