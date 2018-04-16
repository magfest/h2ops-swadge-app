#!/usr/bin/env python3
"""
A simple demonstration game for the MAGLabs 2017 Swadge.
"""

from autobahn.asyncio.wamp import ApplicationSession, ApplicationRunner
from autobahn.wamp import auth
import functools
import asyncio
import aiohttp
import time
import json


class Button:
    """ Button name constants"""

    UP = "up"
    DOWN = "down"
    LEFT = "left"
    RIGHT = "right"
    SELECT = "select"
    START = "start"
    A = "a"
    B = "b"


class Color:
    """Some common colors"""
    RED = 0xff0000
    ORANGE = 0xff7f00
    YELLOW = 0xffff00
    GREEN = 0x00ff00
    CYAN = 0x00ffff
    BLUE = 0x0000ff
    PURPLE = 0x7f00ff
    PINK = 0xff00ff

    WHITE = 0xffffff
    BLACK = 0x000000
    OFF = 0x000000

    RAINBOW = [RED, ORANGE, YELLOW, GREEN, CYAN, BLUE, PURPLE]


def lighten(amt, color):
    """
    Lighten a color by a percent --
    :param amt:
    :param color:
    :return:
    """
    return int(amt * ((color >> 16) & 0xff)) << 16 \
           | int(amt * ((color >> 8) & 0xff)) << 8 \
           | int(amt * (color & 0xff)) & 0xff


# WAMP Realm; doesn't change
WAMP_REALM = "swadges"
WAMP_URL = "ws://api.swadge.com:1337/ws"

# WAMP Credentials; you will get your own later
WAMP_USER = "demo"
WAMP_PASSWORD = "hunter2"

# This is a unique name for this game
# Change this before you run it, otherwise it will conflict!
GAME_ID = "h2ops"

# This is a unique button sequence a swadge can enter to join this game.
# This can be changed at any time, as long as the new value is unique.
# Setting this to the empty string will disable joining by sequence.
# Maximum length is 12; 6 is recommended.
# Buttons are [u]p, [l]eft, [d]own, [r]ight, s[e]lect, [s]tart, [a], [b]
GAME_JOIN_SEQUENCE = "udududlrlrlr"

# This is the name of a location that will cause a swadge to automatically
# join the game without needing to press any buttons. They will also leave
# the game when they are no longer in the location. Setting this to the
# empty string will disable joining by location. If this is set along with
# join by sequence, either of them being triggered will result in a join.
# Note that only one game can "claim" a location at once, so unless you need
# exclusive control over the location, you should just subscribe to that
# location.
#
# Current tracked locations (more may be added; if you'd like to make sure
# a location will be tracked, ask in #circuitboards):
# - panels1
# - gameroom
# - concerts
GAME_JOIN_LOCATION = ""

SETTINGS = {}


class Sender:
    @classmethod
    async def send_message(cls, location, msg):
        with aiohttp.ClientSession() as client:
            headers = {
                'content-type': 'application-json'
            }

            payload = {
                "text": f"*{location}*: {msg}",
            }

            # FIXME put the spam back in
            return

            async with client.request(
                'post',
                SETTINGS['webhook_url'],
                data=json.dumps(payload),
                headers=headers,
            ) as request:
                res = await request.text()


class ButtonAction:
    def __init__(self, message, flag_after=1, message_after=1, cooldown_time=0, hold_time=0):
        self.message = message

        #: Number of clicks before flag is set
        self.flag_after = flag_after

        #: Number of clicks before message is sent
        self.message_after = message_after

        #: Time after a click before another can be registered
        self.cooldown_time = cooldown_time

        #: Time button must be held down before a click is registered
        self.hold_time = hold_time

    def get_config(self):
        return {
            "message": self.message,
            "flag_after": self.flag_after,
            "message_after": self.message_after,
            "cooldown_time": self.cooldown_time,
            "hold_time": self.hold_time,
        }


class Station:
    def __init__(self, name):
        self.name = name

        #: List[PlayerInfo]
        self.swadges = []

        # A map of the buttons to its action
        self.button_actions = {
            Button.UP: ButtonAction('Up Pressed'),
            Button.DOWN: ButtonAction('Down Pressed', hold_time=800)
        }

    def get_config(self):
        return {
            "name": self.name,
            "actions": {
                button: action.get_config() if action else None
                for button, action in self.button_actions.items()
            },
            "badges": {
                str(badge.badge_id): badge for badge in self.swadges
            }
        }


class SwadgeInfo:
    def __init__(self, badge_id, station=None, subscriptions=None, component=None):
        self.badge_id = badge_id

        # The station of this button
        self.station = station

        #: The WAMP component
        self.component = component

        self.button_downs = {
            Button.UP: 0,
            Button.DOWN: 0,
            Button.LEFT: 0,
            Button.RIGHT: 0,
            Button.SELECT: 0,
            Button.START: 0,
            Button.A: 0,
            Button.B: 0,
        }

        self.button_ups = {
            Button.UP: 0,
            Button.DOWN: 0,
            Button.LEFT: 0,
            Button.RIGHT: 0,
            Button.SELECT: 0,
            Button.START: 0,
            Button.A: 0,
            Button.B: 0,
        }

        self.button_counts = {
            Button.UP: 0,
            Button.DOWN: 0,
            Button.LEFT: 0,
            Button.RIGHT: 0,
            Button.SELECT: 0,
            Button.START: 0,
            Button.A: 0,
            Button.B: 0,
        }

        self.flags = []

        # Subscriptions that have been made for the player
        # Needed so we can unsubscribe later
        self.subscriptions = subscriptions or []

    def get_config(self):
        return {
            "badge_id": self.badge_id,
            "station": self.station,
            "button_counts": self.button_counts,
            "flags": self.flags,
            "battery": 100,
        }

    async def do_progress_lights(self, button):
        if not self.station:
            print("no station")
            return

        action = self.station.button_actions.get(button)

        if not action:
            print("no action")
            return

        hold_time = action.hold_time

        if hold_time:
            for i in range(5):
                if self.button_ups[button] <= self.button_downs[button]:
                    await self.set_lights([Color.RED] * (4-i) + [Color.GREEN] * i, brightness=.5)
                    await asyncio.sleep(hold_time / 4000)
                elif self.button_ups[button] - self.button_downs[button] <= hold_time:
                    await self.do_fail_lights()
                    break
                else:
                    break
        else:
            await self.do_ok_lights()

    async def do_ok_lights(self):
        await self.set_lights(brightness=0)
        await asyncio.sleep(.2)
        await self.set_lights(color=Color.GREEN, brightness=.75)
        await asyncio.sleep(.25)
        await self.set_lights(color=Color.CYAN, brightness=.05)

    async def do_fail_lights(self):
        await self.set_lights(brightness=0)
        await asyncio.sleep(.2)
        await self.set_lights(color=Color.RED, brightness=.75)
        await asyncio.sleep(.25)
        await self.set_lights(color=Color.RED, brightness=.05)

    async def button_press(self, button, timestamp):
        print(button, 'press')
        action = self.station.button_actions.get(button)

        if action:
            #self.button_ups[button] = 0
            self.button_downs[button] = timestamp

            if not action.hold_time:
                print(self.station.name, action.message)
                await Sender.send_message(self.station.name, action.message)

            await self.do_progress_lights(button)

    async def reset(self, action_button):
        self.button_counts[action_button] = 0
        self.button_downs[action_button] = 0
        self.button_ups[action_button] = 0

        if self.station:
            action = self.station.button_actions.get(action_button)
            if action:
                self.flags.remove(action.message)

    async def button_release(self, button, timestamp):
        print(button, 'release')
        action = self.station.button_actions.get(button)

        if action and action.hold_time:
            time_since_last = self.button_downs[button] - self.button_ups[button]
            self.button_ups[button] = timestamp

            held_time = timestamp - self.button_downs[button]

            if held_time > action.hold_time:
                if time_since_last > action.cooldown_time:
                    self.button_counts[button] += 1

                    await self.do_ok_lights()

                    if self.button_counts[button] > action.message_after:
                        await Sender.send_message(self.station.name, action.message)
                    else:
                        print(f"Need {action.message_after} presses to send message")

                    if self.button_counts[button] > action.flag_after:
                        self.flags.append(action.message)
                    else:
                        print(f"Need {action.flag_after} presses to set flag")

                    await self.send_update()
                else:
                    print(f"Need to wait {action.cooldown_time} for another button press")
                    await self.do_fail_lights()

                print(self.station.name, action.message)
            else:
                print(f"No go, {held_time} < {action.hold_time}")
                await self.do_fail_lights()

    async def send_update(self):
        self.component.publish('game.h2ops.station_updated', {
            "id": str(self.badge_id),
            "config": self.get_config()
        })

    async def set_lights(self, colors=None, color=Color.WHITE, brightness=.1):
        # Set the lights for the badge to simple colors
        if not colors:
            colors = [color] * 4

        # Note that the order of the lights will be [BOTTOM_LEFT, BOTTOM_RIGHT, TOP_RIGHT, TOP_LEFT]
        self.component.publish('badge.' + str(self.badge_id) + '.lights_static',
                               *(lighten(brightness, c) for c in colors))


class GameComponent(ApplicationSession):
    players = {}
    stations = {}

    def onConnect(self):
        """
        Called by WAMP upon successfully connecting to the crossbar server
        :return: None
        """
        self.join(WAMP_REALM, ["wampcra"], WAMP_USER)

    def onChallenge(self, challenge):
        """
        Called by WAMP for authentication.
        :param challenge: The server's authentication challenge
        :return:          The client's authentication response
        """
        if challenge.method == "wampcra":
            signature = auth.compute_wcs(WAMP_PASSWORD.encode('utf8'),
                                         challenge.extra['challenge'].encode('utf8'))
            return signature.decode('ascii')
        else:
            raise Exception("don't know how to handle authmethod {}".format(challenge.method))

    async def game_register(self):
        """
        Register the game with the server. Should be called after initial connection and any time
        the server requests it.
        :return: None
        """

        res = await self.call('game.register',
                              GAME_ID,
                              sequence=GAME_JOIN_SEQUENCE,
                              location=GAME_JOIN_LOCATION)

        err = res.kwresults.get("error", None)
        if err:
            print("Could not register:", err)
        else:
            # This call returns any players that may have already joined the game to ease restarts
            players = res.kwresults.get("players", [])
            await asyncio.gather(*(self.on_player_join(player) for player in players))

    async def on_button_press(self, button, timestamp=0, badge_id=None):
        """
        Called when a button is pressed.
        :param button:    The name of the button that was pressed
        :param timestamp: The timestamp of the button press, in ms
        :param badge_id:  The ID of the badge that pressed the button
        :return: None
        """

        player = self.players.get(badge_id, None)

        if not player:
            print("Unknown player:", badge_id)
            return

        await player.button_press(button, timestamp)

    async def on_button_release(self, button, timestamp=0, badge_id=None):
        """
        Called when a button is released.
        :param button:    The name of the button that was released
        :param timestamp: The timestamp of the button release, in ms
        :param badge_id:  The ID of the badge that released the button
        :return: None
        """

        player = self.players.get(badge_id, None)

        if not player:
            print("Unknown player:", badge_id)
            return

        # Do something with button released here
        await player.button_release(button, timestamp)

    async def on_player_join(self, badge_id):
        """
        Called when a player joins the game, such as by entering a join sequence or entering a
        designated location.
        :param badge_id: The badge ID of the player who left
        :return: None
        """

        print("Badge #{} joined".format(badge_id))

        # Listen for button presses and releases
        press_sub = await self.subscribe(self.on_button_press, 'badge.' + str(badge_id) + '.button.press')

        # If you want to listen for button releases too, un-comment this and add release_sub to
        # the list of subscriptions below
        release_sub = await self.subscribe(self.on_button_release, 'badge.' + str(badge_id) + '.button.release')

        # Add an entry to keep track of the player's game-state
        self.players[badge_id] = SwadgeInfo(badge_id, station=Station("test"),
                                            component=self, subscriptions=[press_sub])

        await self.players[badge_id].set_lights(color=Color.GREEN)

    async def on_player_leave(self, badge_id):
        """
        Called when a player leaves the game, such as by leaving a designated location.
        :param badge_id: The badge ID of the player who left
        :return: None
        """

        # Make sure we unsubscribe from all this badge's topics
        print("Badge #{} left".format(badge_id))
        await asyncio.gather(*(s.unsubscribe() for s in self.players[badge_id].subscriptions))
        del self.players[badge_id]

    async def get_config(self):
        return {
            "players": [player.get_config() for player in self.players.values()],
            "stations": {id: station.get_config() for id, station in self.stations.items()}
        }

    async def set_station(self, badge_id, station_id):
        player = self.players.get(badge_id)

        if not player:
            return False

        station = self.stations.get(station_id)

        if not station:
            return False

        player.station = station

    async def onJoin(self, details):
        """
        WAMP calls this after successfully joining the realm.
        :param details: Provides information about
        :return: None
        """

        # Subscribe to all necessary things
        await self.subscribe(self.on_player_join, 'game.' + GAME_ID + '.player.join')
        await self.subscribe(self.on_player_leave, 'game.' + GAME_ID + '.player.leave')
        await self.subscribe(self.game_register, 'game.request_register')
        await self.register(self.get_config, 'game.h2ops.get_config')
        await self.register(self.set_station, 'game.h2ops.set_station')
        await self.game_register()

    def onDisconnect(self):
        """
        Called when the WAMP connection is disconnected
        :return: None
        """
        asyncio.get_event_loop().stop()


if __name__ == '__main__':
    if GAME_ID == 'demo_game':
        print("Please change GAME_ID to something else!")
        exit(1)

    global settings

    try:
        with open('h2ops.conf') as f:
            SETTINGS = json.load(f)
    except:
        print("Error! Could not find 'h2ops.conf'")
        exit(1)

    runner = ApplicationRunner(
        WAMP_URL,
        WAMP_REALM,
    )
    runner.run(GameComponent, log_level='info')
