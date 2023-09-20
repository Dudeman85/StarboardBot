from discord.ext import tasks, commands
import discord
import datetime
from zoneinfo import ZoneInfo, available_timezones
import json

MAX_CACHE_SIZE = 30

#By default need to have at least one time
times = [datetime.time(hour=0, minute=0)]

class Scheduler(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.send_message.start()
        self.refresh()
        
    def cog_unload(self):
        self.send_message.cancel()

    #Refresh the list of times
    def refresh(self):
        #If there are no messages don't bother refreshing
        if len(self.bot.data["messages"]) == 0:
            return
        
        #Clear times and add every time from bot
        times = []
        for _, msg in self.bot.data["messages"].items():
            #Get the time from string
            msgTime = msg["time"].split(":")
            hour = int(msgTime[0])
            minute = int(msgTime[1])
            #Create the time object and add it to the list
            time = datetime.time(hour=hour, minute=minute, tzinfo=ZoneInfo(self.bot.data["timezone"]))
            times.append(time)

        #Update the times to run send_messages at
        self.send_message.change_interval(time=times)

    #Run this function every time a messa schedule time is up
    @tasks.loop(time=times)
    async def send_message(self):
        await self.bot.handle_scheduled_message()


class RemindBot(discord.Client):
    async def on_ready(self):
        self.data = {}
        try:
            #Load in the data from json
            with open("save.json") as file:
                self.data = json.load(file)
                
                print("Loaded data from file")

        except Exception as e:
            #If the data file could not be loaded for some reason
            print("Could not open save. Creating default one. " + str(e))

            #Set the default settings
            self.data["timezone"] = "UTC"
            self.data["toChannel"] = "1153254266744606760" #TODO THIS IS VERY TEMPORARY GET THE REAL DEFAULT ID
            self.data["notify"] = ""
            self.data["messages"] = {}
            self.data["messageCache"] = {}
            self.save_data()

        #Create the message scheduler
        self.scheduler = Scheduler(self)

        print(f"Logged in as {self.user}!")

    #Every time someone reacts to this bots message
    async def on_raw_reaction_add(self, payload):
        #If the message is not in the tracked cache ignore reaction
        if str(payload.message_id) not in self.data["messageCache"]:
            return


        """
        #Form the message
        cacheInfo = self.data["messageCache"][str(payload.message_id)]
        
        #For each user set to be notified
        dmID = 1
        for userID in self.data["notify"]:
            #Get the proper message from the user's dms
            sendTo = await self.fetch_user(userID)

            something = sendTo.history()
            channel = discord.utils.get(self.private_channels, id=cacheInfo[dmID])

            for pmChannels in self.private_channels:
                if sendTo in pmChannels:
                    dm = await sendTo.fetch_message(cacheInfo[dmID])

                    #Update the message
                    await dm.edit(content="asdasdasds")         
        """   

    #Every time a message is sent in a channel
    async def on_message(self, message):
        #Don't respond to self
        if message.author == client.user:
            return
        #Only respond in channel named bot-chat
        if message.channel.name != "bot-chat":
            return

        #$timezone [new timezone]
        #Returns the current timezone, or if new timezone is provided switch to that
        if message.content.startswith("$timezone"):
            if len(message.content) > 12:
                #Cut off the $timezone part of the command
                newTimezone = message.content[10:]
                if newTimezone in available_timezones():
                    self.data["timezone"] = newTimezone
                    self.save_data()
                    self.scheduler.refresh()
                    await message.channel.send("Timezone set to " + newTimezone)
                else:
                    await message.channel.send(newTimezone + " is not a valid timezone")
            else:
                #If no new timezone is provided send the current one
                await message.channel.send(f"Current timezone is " + str(self.data["timezone"]) + "\nTo change the timezone use $timezone [new timezone]")

        #$notify [person]
        #Notifies every mentioned person when a message was reacted on
        if(message.content.startswith("$notify")):
            #If no one was mentioned
            if len(message.mentions) == 0:
                await message.channel.send("Usage: $notify [@person]")
                return

            self.data["notify"] = []

            msg = "Notifying "
            for mention in message.mentions:
                #Add them to data
                self.data["notify"].append(mention.id)
                #Format the mentions into a string to be sent as confirmation
                msg += f"<@{mention.id}> "
            await message.channel.send(msg)
            
            self.save_data()

        #$send to channel [#channel]
        #Sends the scheduled messages to specified channel
        if(message.content.startswith("$send to channel")):
            newTargetChannel = message.channel_mentions
            #If no channel name was provided
            if len(newTargetChannel) < 1:
                await message.channel.send("Usage: $send to channel [#channel]")

            self.data["toChannel"] = newTargetChannel[0].id
            await message.channel.send(f"Now sending messages to <#{newTargetChannel[0].id}>")

            self.save_data()
            self.scheduler.refresh()

        #$add message [label], [text], [time (H:M)], [repeat]
        #Schedule a message to be sent at time, optionally repeat on specific week day 
        if(message.content.startswith("$add message")):
            try:
                #Split the important parts of the message into a list
                msgParams = message.content[13:].split(",")
                label = msgParams[0].lstrip()
                text = msgParams[1].lstrip()
                time = msgParams[2].lstrip()
                repeat = msgParams[3].lstrip()

                #If a message with the label already exists, don't add it
                if(label in self.data["messages"]):
                    await message.channel.send("Message with label " + label + " already exists")
                    return

                #Add a new message to the data dict
                newMessage = {"text":text, "time":time, "repeat":repeat}
                self.data["messages"][label] = newMessage
                self.save_data()
                #Remake the scheduler because of time changes
                self.scheduler = Scheduler(self)

                await message.channel.send("Successfully created new message")
            except Exception as e:
                print(e)
                await message.channel.send("Usage: $add message [label] [message] [time] [repeat]")

        #$remove message [label]
        #Removes a scheduled message by label
        if message.content.startswith("$remove message"):
            #If the command doesn't contain the label
            if len(message.content) < 17:
                await message.channel.send("Usage: $remove message [label]")

            #If the label is in messages remove it
            if message.content[16:] in self.data["messages"]:
                self.data["messages"].pop(message.content[16:])
                self.save_data()
                self.scheduler.refresh()
                await message.channel.send("Successfully removed message")
            else:
                await message.channel.send(message.content[16:] + " not in scheduled messages")

        #$list messages
        #Shows the curretly scheduled messages
        if message.content.startswith("$list messages"):
            fullMessage = ""
            #Add every message to the string to be sent
            for label, msg in self.data["messages"].items():
                fullMessage += label + " sends on " + msg["time"] + " every " + msg["repeat"] + ":\n"
                fullMessage += msg["text"] + "\n\n"

            if fullMessage == "":
                fullMessage = "No messages scheduled"

            await message.channel.send(fullMessage)

        #$help
        #Prints the usage of every command
        if(message.content.startswith("$help")):
            await message.channel.send(
                r"""
$help : Prints this message
$notify [@persons] : Notifies every mentioned person when a message was reacted on
$timezone [new timezone] : Returns the current timezone, or if new timezone is provided switch to using that
$send to channel [#channel] : Sends the scheduled messages to specified channel
$list messages : Shows the curretly scheduled messages
$add message [label], [text], [time (H:M)], [repeat] : Schedule a message to be sent at time, optionally repeat on specific week day 
$remove message [label] : Removes a message by label
            """)

    async def handle_scheduled_message(self):
        #Get the channel from saved ID
        channel = self.get_channel(self.data["toChannel"])
        now = datetime.datetime.now()

        #For each message check if it is time to send it
        for label, message in self.data["messages"].items():
            hm = message["time"].split(":")
            hour = hm[0]
            minute = hm[1]

            #If the current time matches the message time send it
            if int(hour) == now.hour and int(minute) == now.minute:
                msg = await channel.send(message["text"])
                #Add the reactions
                await msg.add_reaction(u"\N{WHITE HEAVY CHECK MARK}")
                await msg.add_reaction(u"\N{CROSS MARK}")

                cacheData = [label]
                dm = f"{label}:\n\N{WHITE HEAVY CHECK MARK} :\n\N{CROSS MARK} :"
                #Send the reaction counter dm
                #For each user set to be notified
                for userID in self.data["notify"]:
                    sendTo = await self.fetch_user(userID)
                    dmID = await sendTo.send(dm)
                    cacheData.append(dmID.id)

                #Add the message to cache
                self.data["messageCache"][str(msg.id)] = cacheData
                if len(self.data["messageCache"]) > MAX_CACHE_SIZE:
                    self.data["messageCache"].pop(0)
                self.save_data()

    #Write data to json file
    def save_data(self):
        with open("save.json", "w") as file:
            data = json.dumps(self.data, indent=4)
            file.write(data)


        
intents = discord.Intents.default()
intents.message_content = True
intents.reactions = True

client = RemindBot(intents=intents)

client.run("MTE1MzI1NjcxNzUwNTgxMDQ0NA.G3mCR-.gGmTZGHdFT0GAs580sGXHCNAQnRYa4v1AaOuBY")