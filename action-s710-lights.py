#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# -----------------------------------------------------------------------------
# Snips Lights + Homeassistant
# -----------------------------------------------------------------------------
# Copyright 2019 Patrick Fial
# -----------------------------------------------------------------------------
# Permission is hereby granted, free of charge, to any person obtaining a copy of this software and 
# associated documentation files (the "Software"), to deal in the Software without restriction, 
# including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, 
# and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, 
# subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all copies or substantial 
# portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT 
# LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. 
# IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, 
# WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE 
# SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

# -----------------------------------------------------------------------------
# Imports
# -----------------------------------------------------------------------------

import io
import toml
import requests

from snipsTools import SnipsConfigParser
from hermes_python.hermes import Hermes
from hermes_python.ontology import *

# -----------------------------------------------------------------------------
# global definitions (home assistant service URLs)
# -----------------------------------------------------------------------------

HASS_LIGHTS_ON_SVC = "/api/services/light/turn_on"
HASS_LIGHTS_OFF_SVC = "/api/services/light/turn_off"
HASS_GROUP_ON_SVC = "/api/services/homeassistant/turn_on"
HASS_GROUP_OFF_SVC = "/api/services/homeassistant/turn_off"
HASS_AUTOMATION_ON_SVC = "/api/services/automation/turn_on"
HASS_AUTOMATION_OFF_SVC = "/api/services/automation/turn_off"

# -----------------------------------------------------------------------------
# class LightsHASS
# -----------------------------------------------------------------------------

class LightsHASS(object):

    # -------------------------------------------------------------------------
    # ctor

    def __init__(self, debug = False):

        self.debug = debug

        # parameters

        self.mqtt_host = None
        self.mqtt_user = None
        self.mqtt_pass = None

        self.hass_host = None
        self.hass_token = None
        
        # read config.ini (HASS host + token)

        try:
            self.config = SnipsConfigParser.read_configuration_file("config.ini")
        except Exception as e:
          print("Failed to read config.ini ({})".format(e))
          self.config = None

        try:
          self.read_toml()
        except Exception as e:
          print("Failed to read /etc/snips.toml ({})".format(e))

        self.hass_host = self.config['secret']['hass_host']
        self.hass_token = self.config['secret']['hass_token']
        self.hass_headers = { 'Content-Type': 'application/json', 'Authorization': "Bearer " + self.hass_token }

        if 'confirmation_success' in self.config['secret']:
          self.confirmation_success = self.config['secret']['confirmation_success']
        else:
          self.confirmation_success = "Bestätige"

        if 'confirmation_failure' in self.config['secret']:
          self.confirmation_failure = self.config['secret']['confirmation_failure']
        else:
          self.confirmation_failure = "Ausführung nicht möglich"

        if self.debug:
          print("Connecting to {}@{} ...".format(self.mqtt_user, self.mqtt_host))

        self.start()

    # -----------------------------------------------------------------------------
    # read_toml

    def read_toml(self):
        snips_config = toml.load('/etc/snips.toml')
    
        if 'mqtt' in snips_config['snips-common'].keys():
            self.mqtt_host = snips_config['snips-common']['mqtt']

        if 'mqtt_username' in snips_config['snips-common'].keys():
            self.mqtt_user = snips_config['snips-common']['mqtt_username']

        if 'mqtt_password' in snips_config['snips-common'].keys():
            self.mqtt_pass = snips_config['snips-common']['mqtt_password']

    # -------------------------------------------------------------------------
    # start

    def start(self):
        with Hermes(mqtt_options = MqttOptions(broker_address = self.mqtt_host, username = self.mqtt_user, password = self.mqtt_pass)) as h:
            h.subscribe_intents(self.on_intent).start()

    # -------------------------------------------------------------------------
    # on_intent

    def on_intent(self, hermes, intent_message):
        intent_name = intent_message.intent.intent_name
        site_id = intent_message.site_id
        room_id = None
        lamp_id = None

        # extract mandatory information (lamp_id, room_id)

        try:
            if len(intent_message.slots):
                if len(intent_message.slots.lightType):
                    lamp_id = intent_message.slots.lightType.first().value
                    lamp_id = lamp_id.lower().replace('ä', 'ae').replace('ü','ue').replace('ö', 'oe')
                if len(intent_message.slots.roomName):
                    room_id = intent_message.slots.roomName.first().value
                    room_id = room_id.lower().replace('ä', 'ae').replace('ü','ue').replace('ö', 'oe')
        except:
            pass

        # get corresponding home assistant service-url + payload

        service, data = self.params_of(room_id, lamp_id, site_id, intent_name)

        # fire the service using HA REST API

        if service is not None and data is not None:
          if self.debug:
            print("Intent {}: Firing service [{} -> {}] with [{}]".format(intent_name, self.hass_host, service, data))

          r = requests.post(self.hass_host + service, json = data , headers = self.hass_headers)

          if r.status_code == 200:
            hermes.publish_start_session_notification(intent_message.site_id, self.confirmation_success, "")
          else:
            hermes.publish_start_session_notification(intent_message.site_id, self.confirmation_failure, "")
        else:
          print("Intent {}/parameters not recognized, ignoring".format(intent_name))

    # -------------------------------------------------------------------------
    # params_of

    def params_of(self, room_id, lamp_id, site_id, intent_name):

      if intent_name == 's710:turnOnLight':
        if lamp_id is not None:
          return (HASS_LIGHTS_ON_SVC, {'entity_id': 'light.{}'.format(lamp_id) })
        elif room_id is not None:
          return (HASS_GROUP_ON_SVC, {'entity_id': 'group.lights_{}'.format(room_id) })
        else:
          return (HASS_GROUP_ON_SVC, {'entity_id': 'group.lights_{}'.format(site_id) })

      if intent_name == 's710:turnOffLight':
        if lamp_id is not None:
          return (HASS_LIGHTS_OFF_SVC, {'entity_id': 'light.{}'.format(lamp_id) })
        elif room_id is not None:
          return (HASS_GROUP_OFF_SVC, {'entity_id': 'group.lights_{}'.format(room_id) })
        else:
          return (HASS_GROUP_OFF_SVC, {'entity_id': 'group.lights_{}'.format(site_id) })

      if intent_name == 's710:turnOnAllLights':
        return (HASS_GROUP_ON_SVC, {'entity_id': 'group.all_lights' })
      
      if intent_name == 's710:turnOffAllLights':
        return (HASS_GROUP_OFF_SVC, {'entity_id': 'group.all_lights' })

      if intent_name == 's710:keepLightOn':
        if lamp_id is not None:
          return (HASS_AUTOMATION_ON_SVC, {'entity_id': 'automation.lights_on_{}'.format(lamp_id) })
        elif room_id is not None:
          return (HASS_AUTOMATION_ON_SVC, {'entity_id': 'automation.lights_on_{}'.format(room_id) })
        else:
          return (HASS_AUTOMATION_ON_SVC, {'entity_id': 'automation.lights_on_{}'.format(site_id) })

      if intent_name == 's710:keepLightOff':
        if lamp_id is not None:
          return (HASS_AUTOMATION_OFF_SVC, {'entity_id': 'automation.lights_on_{}'.format(lamp_id) })
        elif room_id is not None:
          return (HASS_AUTOMATION_OFF_SVC, {'entity_id': 'automation.lights_on_{}'.format(room_id) })
        else:
          return (HASS_AUTOMATION_OFF_SVC, {'entity_id': 'automation.lights_on_{}'.format(site_id) })

      return (None, None)

# -----------------------------------------------------------------------------
# main
# -----------------------------------------------------------------------------

if __name__ == "__main__":
    LightsHASS()
