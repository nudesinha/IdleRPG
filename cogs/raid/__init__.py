"""
The IdleRPG Discord Bot
Copyright (C) 2018-2021 Diniboy and Gelbpunkt

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with this program.  If not, see <https://www.gnu.org/licenses/>.
"""
import asyncio
import datetime
import re

from decimal import Decimal

import discord

from discord.enums import ButtonStyle
from discord.errors import NotFound
from discord.ext import commands
from discord.ui.button import Button

from classes.classes import Raider
from classes.classes import from_string as class_from_string
from classes.converters import IntGreaterThan
from cogs.shard_communication import user_on_cooldown as user_cooldown
from utils import random
from utils.checks import AlreadyRaiding, has_char, is_gm, is_god
from utils.i18n import _, locale_doc
from utils.joins import JoinView


def raid_channel():
    def predicate(ctx):
        return (
            ctx.bot.config.bot.is_beta
            or ctx.channel.id == ctx.bot.config.game.raid_channel
        )

    return commands.check(predicate)


def raid_free():
    async def predicate(ctx):
        ttl = await ctx.bot.redis.execute_command("TTL", "special:raid")
        if ttl != -2:
            raise AlreadyRaiding("There is already a raid ongoing.")
        return True

    return commands.check(predicate)


def is_cm():
    def predicate(ctx) -> bool:
        return (
            ctx.guild.id == ctx.bot.config.game.support_server_id
            and 491353140042530826 in [r.id for r in ctx.author.roles]
        )

    return commands.check(predicate)


class Raid(commands.Cog):
    """Raids are only available in the support server. Use the support command for an invite link."""

    def __init__(self, bot):
        self.bot = bot

        self.boss = None
        self.allow_sending = discord.PermissionOverwrite(
            send_messages=True, read_messages=True
        )
        self.deny_sending = discord.PermissionOverwrite(
            send_messages=False, read_messages=False
        )
        self.read_only = discord.PermissionOverwrite(
            send_messages=False, read_messages=True
        )

    def getfinaldmg(self, damage: Decimal, defense):
        return v if (v := damage - defense) > 0 else 0

    async def set_raid_timer(self):
        await self.bot.redis.execute_command(
            "SET",
            "special:raid",
            "running",  # ctx isn't available
            "EX",
            3600,  # signup period + time until timeout
        )

    async def clear_raid_timer(self):
        await self.bot.redis.execute_command("DEL", "special:raid")

    @is_gm()
    @commands.command(hidden=True)
    async def alterraid(self, ctx, newhp: IntGreaterThan(0)):
        """[Bot Admin only] Change a raid boss' HP."""
        if not self.boss:
            return await ctx.send("No Boss active!")
        self.boss.update(hp=newhp, initial_hp=newhp)
        try:
            spawnmsg = await ctx.channel.fetch_message(self.boss["message"])
            edited_embed = spawnmsg.embeds[0]
            edited_embed.description = re.sub(
                r"\d+(,*\d)+ HP", f"{newhp:,.0f} HP", edited_embed.description
            )
            edited_embed.set_image(url="attachment://dragon.webp")
            await spawnmsg.edit(embed=edited_embed)
        except discord.NotFound:
            return await ctx.send("Could not edit Boss HP!")
        await ctx.send("Boss HP updated!")

    @is_gm()
    @raid_channel()
    @raid_free()
    @commands.command(hidden=True, brief=_("Start a Ragnorak raid"))
    async def spawn(self, ctx, hp: IntGreaterThan(0)):
        """[Bot Admin only] Starts a raid."""
        await self.set_raid_timer()

        self.boss = {"hp": hp, "initial_hp": hp, "min_dmg": 100, "max_dmg": 500}
        joined = []

        for member_id in self.bot.cogs["Patreon"].ruby_or_above:
            try:
                joined.append(await ctx.guild.fetch_member(member_id))
            except NotFound:
                pass

        await ctx.channel.set_permissions(
            ctx.guild.default_role,
            overwrite=self.read_only,
        )

        fi = discord.File("assets/other/dragon.jpeg")
        em = discord.Embed(
            title="Ragnorak Spawned",
            description=(
                f"This boss has {self.boss['hp']:,.0f} HP and has high-end loot!\nThe"
                " evil dragon will be vulnerable in 15 Minutes!"
            ),
            color=self.bot.config.game.primary_colour,
        )
        em.set_image(url="attachment://dragon.jpeg")
        em.set_thumbnail(url=ctx.author.display_avatar.url)

        view = JoinView(
            Button(style=ButtonStyle.primary, label="Join the raid!"),
            message=_("You joined the raid."),
            timeout=60 * 15,
        )

        spawnmsg = await ctx.send(embed=em, file=fi, view=view)

        self.boss.update(message=spawnmsg.id)

        if self.bot.config.bot.is_beta:
            if self.bot.config.bot.is_custom:
                summary_channel = self.bot.get_channel(113920198436952882)
                raid_ping = await summary_channel.send(
                    "@everyone Ragnorak spawned! 15 Minutes until he is vulnerable...",
                    allowed_mentions=discord.AllowedMentions.all(),
                )
                try:
                    await raid_ping.publish()
                except discord.Forbidden:
                    await summary_channel.send(
                        #"Error! Couldn't publish message. Please publish manually"
                        #f" {ctx.author.mention}"
                    )
                else:
                    await summary_channel.send(
                        "Message has been published!", delete_after=10
                    )

            await asyncio.sleep(300)
            await ctx.send("**The dragon will be vulnerable in 10 minutes**")
            await asyncio.sleep(300)
            await ctx.send("**The dragon will be vulnerable in 5 minutes**")
            await asyncio.sleep(180)
            await ctx.send("**The dragon will be vulnerable in 2 minutes**")
            await asyncio.sleep(60)
            await ctx.send("**The dragon will be vulnerable in 1 minute**")
            await asyncio.sleep(30)
            await ctx.send("**The dragon will be vulnerable in 30 seconds**")
            await asyncio.sleep(20)
            await ctx.send("**The dragon will be vulnerable in 10 seconds**")
            await asyncio.sleep(10)
        else:
            await asyncio.sleep(300)
            await ctx.send("**The dragon will be vulnerable in 10 minutes**")
            await asyncio.sleep(300)
            await ctx.send("**The dragon will be vulnerable in 5 minutes**")
            await asyncio.sleep(180)
            await ctx.send("**The dragon will be vulnerable in 2 minutes**")
            await asyncio.sleep(60)
            await ctx.send("**The dragon will be vulnerable in 1 minute**")
            await asyncio.sleep(30)
            await ctx.send("**The dragon will be vulnerable in 30 seconds**")
            await asyncio.sleep(20)
            await ctx.send("**The dragon will be vulnerable in 10 seconds**")
            await asyncio.sleep(10)

        view.stop()

        await ctx.send(
            "**The dragon is vulnerable! Fetching participant data... Hang on!**"
        )

        raid = {}

        joined.extend(view.joined)

        async with self.bot.pool.acquire() as conn:
            for u in joined:
                if not (
                    profile := await conn.fetchrow(
                        'SELECT * FROM profile WHERE "user"=$1;', u.id
                    )
                ):
                    continue
                dmg, deff = await self.bot.get_raidstats(
                    u,
                    atkmultiply=profile["atkmultiply"],
                    defmultiply=profile["defmultiply"],
                    classes=profile["class"],
                    race=profile["race"],
                    guild=profile["guild"],
                    conn=conn,
                )
                raid[u] = {"hp": 250, "armor": deff, "damage": dmg}

        raiders_joined = len(raid)
        await ctx.send(f"**Done getting data! {raiders_joined} Raiders joined.**")
        start = datetime.datetime.utcnow()

        while (
            self.boss["hp"] > 0
            and len(raid) > 0
            and datetime.datetime.utcnow() < start + datetime.timedelta(minutes=45)
        ):
            target = random.choice(list(raid.keys()))  # the guy it will attack
            dmg = random.randint(
                self.boss["min_dmg"], self.boss["max_dmg"]
            )  # effective damage the dragon does
            finaldmg = self.getfinaldmg(dmg, raid[target]["armor"])
            raid[target]["hp"] -= finaldmg  # damage dealt
            if raid[target]["hp"] > 0:
                em = discord.Embed(
                    title="Ragnarok attacked!",
                    description=f"{target} now has {raid[target]['hp']} HP!",
                    colour=0xFFB900,
                )
            else:
                em = discord.Embed(
                    title="Ragnarok attacked!",
                    description=f"{target} died!",
                    colour=0xFFB900,
                )
            em.add_field(
                name="Theoretical Damage", value=finaldmg + raid[target]["armor"]
            )
            em.add_field(name="Shield", value=raid[target]["armor"])
            em.add_field(name="Effective Damage", value=finaldmg)
            em.set_author(name=str(target), icon_url=target.display_avatar.url)
            em.set_thumbnail(url=f"https://i.imgur.com/vyumja8.png")
            await ctx.send(target.mention, embed=em)
            if raid[target]["hp"] <= 0:
                del raid[target]
            dmg_to_take = sum(i["damage"] for i in raid.values())
            self.boss["hp"] -= dmg_to_take
            await asyncio.sleep(4)
            em = discord.Embed(title="The raid attacked Ragnarok!", colour=0xFF5C00)
            em.set_thumbnail(url=f"https://i.imgur.com/jxtVg6a.png")
            em.add_field(name="Damage", value=dmg_to_take)
            if self.boss["hp"] > 0:
                em.add_field(name="HP left", value=self.boss["hp"])
            else:
                em.add_field(name="HP left", value="Dead!")
            await ctx.send(embed=em)
            await asyncio.sleep(4)

        if len(raid) == 0:
            m = await ctx.send("The raid was all wiped!")
            await m.add_reaction("\U0001F1EB")
            summary_text = (
                "Emoji_here The raid was all wiped! Ragnarok had"
                f" **{self.boss['hp']:,.3f}** health remaining. Better luck next time."
            )
        elif self.boss["hp"] < 1:
            raid_duration = datetime.datetime.utcnow() - start
            minutes = (raid_duration.seconds % 3600) // 60
            seconds = raid_duration.seconds % 60
            summary_duration = f"{minutes} minutes, {seconds} seconds"

            await ctx.channel.set_permissions(
                ctx.guild.default_role,
                overwrite=self.allow_sending,
            )

            highest_bid = [
                356_091_260_429_402_122,
                0,
            ]  # userid, amount

            def check(msg):
                try:
                    val = int(msg.content)
                except ValueError:
                    return False
                if msg.channel.id != ctx.channel.id or (msg.author not in raid):
                    return False
                if not val > highest_bid[1]:
                    return False
                if (
                    msg.author.id == highest_bid[0]
                ):  # don't allow a player to outbid themselves
                    return False
                return True

            page = commands.Paginator()
            for u in list(raid.keys()):
                page.add_line(u.mention)
            page.add_line(
                "The raid killed the boss!\nHe dropped a"
                f" {self.bot.cogs['Crates'].emotes.legendary} Legendary Crate!\nThe highest"
                " bid for it wins <:roosip:505447694408482846>\nSimply type how much"
                " you bid!"
            )
            for p in page.pages:
                await ctx.send(p[4:-4])

            while True:
                try:
                    msg = await self.bot.wait_for("message", timeout=60, check=check)
                except asyncio.TimeoutError:
                    break
                bid = int(msg.content)
                money = await self.bot.pool.fetchval(
                    'SELECT money FROM profile WHERE "user"=$1;', msg.author.id
                )
                if money and money >= bid:
                    highest_bid = [msg.author.id, bid]
                    await ctx.send(f"{msg.author.mention} bids **${msg.content}**!")
            msg = await ctx.send(
                f"Auction done! Winner is <@{highest_bid[0]}> with"
                f" **${highest_bid[1]}**!\nGiving Legendary Crate..."
            )
            money = await self.bot.pool.fetchval(
                'SELECT money FROM profile WHERE "user"=$1;', highest_bid[0]
            )
            if money >= highest_bid[1]:
                async with self.bot.pool.acquire() as conn:
                    await conn.execute(
                        'UPDATE profile SET "money"="money"-$1,'
                        ' "crates_legendary"="crates_legendary"+1 WHERE "user"=$2;',
                        highest_bid[1],
                        highest_bid[0],
                    )
                    await self.bot.log_transaction(
                        ctx,
                        from_=highest_bid[0],
                        to=2,
                        subject="money",
                        data={"Amount": highest_bid[1]},
                        conn=conn,
                    )
                await msg.edit(content=f"{msg.content} Done!")
                summary_crate = (
                    f"Emoji_here Legendary crate {self.bot.cogs['Crates'].emotes.legendary} "
                    f"sold to: **<@{highest_bid[0]}>** for **${highest_bid[1]:,.0f}**"
                )
            else:
                await ctx.send(
                    f"<@{highest_bid[0]}> spent the money in the meantime... Meh!"
                    " Noone gets it then, pah!\nThis incident has been reported and"
                    " they will get banned if it happens again. Cheers!"
                )
                summary_crate = (
                    "Emoji_here The Legendary Crate was not given to anyone since the"
                    f" supposed winning bidder <@{highest_bid[0]}> spent the money in"
                    " the meantime. They will get banned if it happens again."
                )

            cash_pool = int(self.boss["initial_hp"] / 4)
            survivors = len(raid)
            cash = int(cash_pool / survivors)  # what da hood gets per survivor
            users = [u.id for u in raid]
            await self.bot.pool.execute(
                'UPDATE profile SET "money"="money"+$1 WHERE "user"=ANY($2);',
                cash,
                users,
            )
            await ctx.send(
                f"**Gave ${cash:,.0f} of Ragnarok's ${cash_pool:,.0f} drop to all"
                " survivors!**"
            )

            summary_text = (
                f"Emoji_here Defeated in: **{summary_duration}**\n"
                f"{summary_crate}\n"
                f"Emoji_here Payout per survivor: **${cash:,.0f}**\n"
                f"Emoji_here Survivors: **{survivors}**"
            )

        else:
            m = await ctx.send(
                "The raid did not manage to kill Ragnarok within 45 Minutes... He"
                " disappeared!"
            )
            await m.add_reaction("\U0001F1EB")
            summary_text = (
                "Emoji_here The raid did not manage to kill Ragnarok within 45"
                f" Minutes... He disappeared with **{self.boss['hp']:,.3f}** health"
                " remaining."
            )

        await asyncio.sleep(30)
        await ctx.channel.set_permissions(
            ctx.guild.default_role,
            overwrite=self.deny_sending,
        )
        await self.clear_raid_timer()

        if self.bot.config.bot.is_beta:
            summary = (
                "**Raid result:**\n"
                f"Emoji_here Health: **{self.boss['initial_hp']:,.0f}**\n"
                f"{summary_text}\n"
                f"Emoji_here Raiders joined: **{raiders_joined}**"
            )
            summary = summary.replace(
                "Emoji_here",
                ":small_blue_diamond:" if self.boss["hp"] < 1 else ":vibration_mode:",
            )
            summary_msg = await summary_channel.send(summary)
            try:
                await summary_msg.publish()
            except discord.Forbidden:
                await summary_channel.send(
                    "Error! Couldn't publish message. Please publish manually"
                    f" {ctx.author.mention}"
                )
            else:
                await summary_channel.send(
                    "Message has been published!", delete_after=10
                )

        self.boss = None

    @is_god()
    @raid_free()
    @commands.command(hidden=True, brief=_("Start a Kvothe raid"))
    async def kvothespawn(self, ctx, scrael: IntGreaterThan(1)):
        """[Kvothe only] Starts a raid."""
        await self.set_raid_timer()
        scrael = [{"hp": random.randint(80, 100), "id": i + 1} for i in range(scrael)]

        view = JoinView(
            Button(style=ButtonStyle.primary, label="Join the raid!"),
            message=_("You joined the raid."),
            timeout=60 * 15,
        )

        await ctx.send(
            """
The cthae has gathered an army of scrael. Fight for your life!

**Only Kvothe's followers may join.**""",
            file=discord.File("assets/other/cthae.webp"),
            view=view,
        )
        if not self.bot.config.bot.is_beta:
            await asyncio.sleep(300)
            await ctx.send("**The scrael arrive in 10 minutes**")
            await asyncio.sleep(300)
            await ctx.send("**The scrael arrive in 5 minutes**")
            await asyncio.sleep(180)
            await ctx.send("**The scrael arrive in 2 minutes**")
            await asyncio.sleep(60)
            await ctx.send("**The scrael arrive in 1 minute**")
            await asyncio.sleep(30)
            await ctx.send("**The scrael arrive in 30 seconds**")
            await asyncio.sleep(20)
            await ctx.send("**The scrael arrive in 10 seconds**")
            await asyncio.sleep(10)
            await ctx.send(
                "**The scrael arrived! Fetching participant data... Hang on!**"
            )
        else:
            await asyncio.sleep(60)

        view.stop()

        async with self.bot.pool.acquire() as conn:
            raid = {}
            for u in view.joined:
                if (
                    not (
                        profile := await conn.fetchrow(
                            'SELECT * FROM profile WHERE "user"=$1;', u.id
                        )
                    )
                    or profile["god"] != "Kvothe"
                ):
                    continue
                try:
                    dmg, deff = await self.bot.get_raidstats(
                        u,
                        atkmultiply=profile["atkmultiply"],
                        defmultiply=profile["defmultiply"],
                        classes=profile["class"],
                        race=profile["race"],
                        guild=profile["guild"],
                        god=profile["god"],
                        conn=conn,
                    )
                except ValueError:
                    continue
                raid[u] = {"hp": 100, "armor": deff, "damage": dmg, "kills": 0}

        await ctx.send("**Done getting data!**")

        start = datetime.datetime.utcnow()

        while (
            len(scrael) > 0
            and len(raid) > 0
            and datetime.datetime.utcnow() < start + datetime.timedelta(minutes=45)
        ):
            target, target_data = random.choice(list(raid.items()))
            dmg = random.randint(35, 65)
            dmg = self.getfinaldmg(
                dmg, target_data["armor"] * Decimal(random.choice(["0.4", "0.5"]))
            )
            target_data["hp"] -= dmg
            em = discord.Embed(title=f"Scrael left: `{len(scrael)}`", colour=0x000000)
            em.add_field(name="Scrael HP", value=f"{scrael[0]['hp']} HP left")
            if target_data["hp"] > 0:
                em.add_field(
                    name="Attack", value=f"Scrael is fighting against `{target}`"
                )
            else:
                em.add_field(name="Attack", value=f"Scrael killed `{target}`")
            em.add_field(
                name="Scrael Damage", value=f"Has dealt `{dmg}` damage to `{target}`"
            )
            em.set_image(url=f"{self.bot.BASE_URL}/scrael.jpg")
            await ctx.send(embed=em)
            if target_data["hp"] <= 0:
                del raid[target]
                if len(raid) == 0:  # no more raiders
                    break
            scrael[0]["hp"] -= target_data["damage"]
            await asyncio.sleep(7)
            em = discord.Embed(title=f"Heroes left: `{len(raid)}`", colour=0x009900)
            em.set_author(
                name=f"Hero ({target})", icon_url=f"{self.bot.BASE_URL}/swordsman1.jpg"
            )
            em.add_field(
                name="Hero HP", value=f"`{target}` got {target_data['hp']} HP left"
            )
            if scrael[0]["hp"] > 0:
                em.add_field(
                    name="Hero attack",
                    value=(
                        f"Is attacking the scrael and dealt `{target_data['damage']}`"
                        " damage"
                    ),
                )
            else:
                money = random.randint(250, 750)
                await self.bot.pool.execute(
                    'UPDATE profile SET "money"="money"+$1 WHERE "user"=$2;',
                    money,
                    target.id,
                )
                scrael.pop(0)
                em.add_field(
                    name="Hero attack", value=f"Killed the scrael and received ${money}"
                )
                if raid.get(target, None):
                    raid[target]["kills"] += 1
            em.set_image(url=f"{self.bot.BASE_URL}/swordsman2.jpg")
            await ctx.send(embed=em)
            await asyncio.sleep(7)

        if len(scrael) == 0:
            most_kills = sorted(raid.items(), key=lambda x: -(x[1]["kills"]))[0][0]
            async with self.bot.pool.acquire() as conn:
                await conn.execute(
                    'UPDATE profile SET "crates_legendary"="crates_legendary"+$1 WHERE'
                    ' "user"=$2;',
                    1,
                    most_kills.id,
                )
                await self.bot.log_transaction(
                    ctx,
                    from_=1,
                    to=most_kills.id,
                    subject="crates",
                    data={"Rarity": "legendary", "Amount": 1},
                    conn=conn,
                )
            await ctx.send(
                "The scrael were defeated! Our most glorious hero,"
                f" {most_kills.mention}, has received Kvothe's grace, a"
                f" {self.bot.cogs['Crates'].emotes.legendary}."
            )
        elif len(raid) == 0:
            await ctx.send(
                "The scrael have extinguished life in Kvothe's temple! All heroes died!"
            )
        await self.clear_raid_timer()

    @is_god()
    @raid_free()
    @commands.command(hidden=True, brief=_("Start an Eden raid"))
    async def edenspawn(self, ctx, hp: IntGreaterThan(0)):
        """[Eden only] Starts a raid."""
        await self.set_raid_timer()
        self.boss = {"hp": hp, "min_dmg": 100, "max_dmg": 500}
        await ctx.channel.set_permissions(
            ctx.guild.default_role,
            overwrite=self.read_only,
        )

        view = JoinView(
            Button(style=ButtonStyle.primary, label="Join the raid!"),
            message=_("You joined the raid."),
            timeout=60 * 15,
        )

        await ctx.send(
            f"""
The guardian of the gate to the garden has awoken! To gain entry to the Garden of Sanctuary that lays behind the gate you must defeat the guardian.
This boss has {self.boss['hp']} HP and will be vulnerable in 15 Minutes

**Only followers of Eden may join.**
""",
            file=discord.File("assets/other/guardian.webp"),
            view=view,
        )
        if not self.bot.config.bot.is_beta:
            await asyncio.sleep(300)
            await ctx.send("**The guardian will be vulnerable in 10 minutes**")
            await asyncio.sleep(300)
            await ctx.send("**The guardian will be vulnerable in 5 minutes**")
            await asyncio.sleep(180)
            await ctx.send("**The guardian will be vulnerable in 2 minutes**")
            await asyncio.sleep(60)
            await ctx.send("**The guardian will be vulnerable in 1 minute**")
            await asyncio.sleep(30)
            await ctx.send("**The guardian will be vulnerable in 30 seconds**")
            await asyncio.sleep(20)
            await ctx.send("**The guardian will be vulnerable in 10 seconds**")
            await asyncio.sleep(10)
        else:
            await asyncio.sleep(60)

        view.stop()

        await ctx.send(
            "**The guardian is vulnerable! Fetching participant data... Hang on!**"
        )

        async with self.bot.pool.acquire() as conn:
            raid = {}
            for u in view.joined:
                if (
                    not (
                        profile := await conn.fetchrow(
                            'SELECT * FROM profile WHERE "user"=$1;', u.id
                        )
                    )
                    or profile["god"] != "Eden"
                ):
                    continue
                try:
                    dmg, deff = await self.bot.get_raidstats(
                        u,
                        atkmultiply=profile["atkmultiply"],
                        defmultiply=profile["defmultiply"],
                        classes=profile["class"],
                        race=profile["race"],
                        guild=profile["guild"],
                        god=profile["god"],
                        conn=conn,
                    )
                except ValueError:
                    continue
                raid[u] = {"hp": 250, "armor": deff, "damage": dmg}

        await ctx.send("**Done getting data!**")

        start = datetime.datetime.utcnow()

        while (
            self.boss["hp"] > 0
            and len(raid) > 0
            and datetime.datetime.utcnow() < start + datetime.timedelta(minutes=45)
        ):
            target = random.choice(list(raid.keys()))  # the guy it will attack
            dmg = random.randint(self.boss["min_dmg"], self.boss["max_dmg"])
            dmg = self.getfinaldmg(dmg, raid[target]["armor"])
            raid[target]["hp"] -= dmg  # damage dealt
            if raid[target]["hp"] > 0:
                em = discord.Embed(
                    title="The Guardian attacks the seekers of the garden!",
                    description=f"{target} now has {raid[target]['hp']} HP!",
                    colour=0xFFB900,
                )
            else:
                em = discord.Embed(
                    title="The Guardian attacks the seekers of the garden!",
                    description=f"{target} died!",
                    colour=0xFFB900,
                )
            em.add_field(name="Theoretical Damage", value=dmg + raid[target]["armor"])
            em.add_field(name="Shield", value=raid[target]["armor"])
            em.add_field(name="Effective Damage", value=dmg)
            em.set_author(name=str(target), icon_url=target.display_avatar.url)
            em.set_thumbnail(url=f"{self.bot.BASE_URL}/guardian_small.jpg")
            await ctx.send(embed=em)
            if raid[target]["hp"] <= 0:
                del raid[target]
            dmg_to_take = sum(i["damage"] for i in raid.values())
            self.boss["hp"] -= dmg_to_take
            await asyncio.sleep(4)
            em = discord.Embed(
                title="The seekers attacked the Guardian!", colour=0xFF5C00
            )
            em.set_thumbnail(url=f"{self.bot.BASE_URL}/eden_followers.jpg")
            em.add_field(name="Damage", value=dmg_to_take)
            if self.boss["hp"] > 0:
                em.add_field(name="HP left", value=self.boss["hp"])
            else:
                em.add_field(name="HP left", value="Dead!")
            await ctx.send(embed=em)
            await asyncio.sleep(4)

        if len(raid) == 0:
            await ctx.send("The raid was all wiped!")
        elif self.boss["hp"] < 1:
            await ctx.channel.set_permissions(
                ctx.guild.default_role,
                overwrite=self.allow_sending,
            )
            winner = random.choice(list(raid.keys()))
            await self.bot.pool.execute(
                'UPDATE profile SET "crates_legendary"="crates_legendary"+1 WHERE'
                ' "user"=$1;',
                winner.id,
            )
            await ctx.send(
                "The guardian was defeated, the seekers can enter the garden! Eden has"
                f" gracefully given {winner.mention} a legendary crate for their"
                " efforts."
            )

            cash = int(hp / 4 / len(raid))  # what da hood gets per survivor
            users = [u.id for u in raid]
            await self.bot.pool.execute(
                'UPDATE profile SET money=money+$1 WHERE "user"=ANY($2);',
                cash,
                users,
            )
            await ctx.send(
                f"**Gave ${cash} of the Guardian's ${int(hp / 4)} drop to all"
                " survivors!**"
            )

        else:
            await ctx.send(
                "The raid did not manage to kill the Guardian within 45 Minutes... The"
                " entrance remains blocked!"
            )

        await asyncio.sleep(30)
        await ctx.channel.set_permissions(
            ctx.guild.default_role,
            overwrite=self.deny_sending,
        )
        await self.clear_raid_timer()
        self.boss = None

    @is_god()
    @raid_free()
    @commands.command(hidden=True, brief=_("Start a CHamburr raid"))
    async def chamburrspawn(self, ctx, hp: IntGreaterThan(0)):
        """[CHamburr only] Starts a raid."""
        await self.set_raid_timer()
        self.boss = {"hp": hp, "min_dmg": 100, "max_dmg": 500}
        await ctx.channel.set_permissions(
            ctx.guild.default_role,
            overwrite=self.read_only,
        )

        view = JoinView(
            Button(style=ButtonStyle.primary, label="Join the raid!"),
            message=_("You joined the raid."),
            timeout=60 * 15,
        )

        await ctx.send(
            f"""
*Time to eat the hamburger! No, this time, the hamburger will eat you up...*

This boss has {self.boss['hp']} HP and has high-end loot!
The hamburger will be vulnerable in 15 Minutes

**Only followers of CHamburr may join.**""",
            file=discord.File("assets/other/hamburger.webp"),
            view=view,
        )
        if not self.bot.config.bot.is_beta:
            await asyncio.sleep(300)
            await ctx.send("**The hamburger will be vulnerable in 10 minutes**")
            await asyncio.sleep(300)
            await ctx.send("**The hamburger will be vulnerable in 5 minutes**")
            await asyncio.sleep(180)
            await ctx.send("**The hamburger will be vulnerable in 2 minutes**")
            await asyncio.sleep(60)
            await ctx.send("**The hamburger will be vulnerable in 1 minute**")
            await asyncio.sleep(30)
            await ctx.send("**The hamburger will be vulnerable in 30 seconds**")
            await asyncio.sleep(20)
            await ctx.send("**The hamburger will be vulnerable in 10 seconds**")
            await asyncio.sleep(10)
        else:
            await asyncio.sleep(60)

        view.stop()

        await ctx.send(
            "**The hamburger is vulnerable! Fetching participant data... Hang on!**"
        )

        async with self.bot.pool.acquire() as conn:
            raid = {}
            for u in view.joined:
                if (
                    not (
                        profile := await conn.fetchrow(
                            'SELECT * FROM profile WHERE "user"=$1;', u.id
                        )
                    )
                    or profile["god"] != "CHamburr"
                ):
                    continue
                try:
                    dmg, deff = await self.bot.get_raidstats(
                        u,
                        atkmultiply=profile["atkmultiply"],
                        defmultiply=profile["defmultiply"],
                        classes=profile["class"],
                        race=profile["race"],
                        guild=profile["guild"],
                        god=profile["god"],
                        conn=conn,
                    )
                except ValueError:
                    continue
                raid[u] = {"hp": 250, "armor": deff, "damage": dmg}

        await ctx.send("**Done getting data!**")

        start = datetime.datetime.utcnow()

        while (
            self.boss["hp"] > 0
            and len(raid) > 0
            and datetime.datetime.utcnow() < start + datetime.timedelta(minutes=45)
        ):
            target = random.choice(list(raid.keys()))  # the guy it will attack
            dmg = random.randint(self.boss["min_dmg"], self.boss["max_dmg"])
            dmg = self.getfinaldmg(dmg, raid[target]["armor"])
            raid[target]["hp"] -= dmg  # damage dealt
            if raid[target]["hp"] > 0:
                em = discord.Embed(
                    title="Hamburger attacked!",
                    description=f"{target} now has {raid[target]['hp']} HP!",
                    colour=0xFFB900,
                )
            else:
                em = discord.Embed(
                    title="Hamburger attacked!",
                    description=f"{target} died!",
                    colour=0xFFB900,
                )
            em.add_field(name="Theoretical Damage", value=dmg + raid[target]["armor"])
            em.add_field(name="Shield", value=raid[target]["armor"])
            em.add_field(name="Effective Damage", value=dmg)
            em.set_author(name=str(target), icon_url=target.display_avatar.url)
            em.set_thumbnail(url=f"{self.bot.BASE_URL}/hamburger.jpg")
            await ctx.send(embed=em)
            if raid[target]["hp"] <= 0:
                del raid[target]
            dmg_to_take = sum(i["damage"] for i in raid.values())
            self.boss["hp"] -= dmg_to_take
            await asyncio.sleep(4)
            em = discord.Embed(
                title="The raid attacked the hamburger!", colour=0xFF5C00
            )
            em.set_thumbnail(url=f"https://i.imgur.com/jxtVg6a.png")
            em.add_field(name="Damage", value=dmg_to_take)
            if self.boss["hp"] > 0:
                em.add_field(name="HP left", value=self.boss["hp"])
            else:
                em.add_field(name="HP left", value="Dead!")
            await ctx.send(embed=em)
            await asyncio.sleep(4)

        if len(raid) == 0:
            await ctx.send("The raid was all wiped!")
        elif self.boss["hp"] < 1:
            await ctx.channel.set_permissions(
                ctx.guild.default_role,
                overwrite=self.allow_sending,
            )
            highest_bid = [
                356_091_260_429_402_122,
                0,
            ]  # userid, amount

            def check(msg):
                if (
                    msg.channel.id != ctx.channel.id
                    or (not msg.content.isdigit())
                    or (msg.author not in raid)
                ):
                    return False
                if not (int(msg.content) > highest_bid[1]):
                    return False
                if (
                    msg.author.id == highest_bid[0]
                ):  # don't allow a player to outbid themselves
                    return False
                return True

            page = commands.Paginator()
            for u in list(raid.keys()):
                page.add_line(u.mention)
            page.add_line(
                "The raid killed the boss!\nHe dropped a"
                f" {self.bot.cogs['Crates'].emotes.legendary} Legendary Crate!\nThe highest"
                " bid for it wins <:roosip:505447694408482846>\nSimply type how much"
                " you bid!"
            )
            for p in page.pages:
                await ctx.send(p[4:-4])

            while True:
                try:
                    msg = await self.bot.wait_for("message", timeout=60, check=check)
                except asyncio.TimeoutError:
                    break
                bid = int(msg.content)
                money = await self.bot.pool.fetchval(
                    'SELECT money FROM profile WHERE "user"=$1;', msg.author.id
                )
                if money and money >= bid:
                    highest_bid = [msg.author.id, bid]
                    await ctx.send(f"{msg.author.mention} bids **${msg.content}**!")
            msg = await ctx.send(
                f"Auction done! Winner is <@{highest_bid[0]}> with"
                f" **${highest_bid[1]}**!\nGiving Legendary Crate..."
            )
            money = await self.bot.pool.fetchval(
                'SELECT money FROM profile WHERE "user"=$1;', highest_bid[0]
            )
            if money >= highest_bid[1]:
                async with self.bot.pool.acquire() as conn:
                    await conn.execute(
                        'UPDATE profile SET "money"="money"-$1,'
                        ' "crates_legendary"="crates_legendary"+1 WHERE "user"=$2;',
                        highest_bid[1],
                        highest_bid[0],
                    )
                    await self.bot.log_transaction(
                        ctx,
                        from_=highest_bid[0],
                        to=2,
                        subject="money",
                        data={"Amount": highest_bid[1]},
                        conn=conn,
                    )
                await msg.edit(content=f"{msg.content} Done!")
            else:
                await ctx.send(
                    f"<@{highest_bid[0]}> spent the money in the meantime... Meh!"
                    " Noone gets it then, pah!\nThis incident has been reported and"
                    " they will get banned if it happens again. Cheers!"
                )

            cash = int(hp / 4 / len(raid))  # what da hood gets per survivor
            users = [u.id for u in raid]
            await self.bot.pool.execute(
                'UPDATE profile SET money=money+$1 WHERE "user"=ANY($2);',
                cash,
                users,
            )
            await ctx.send(
                f"**Gave ${cash} of the hamburger's ${int(hp / 4)} drop to all"
                " survivors!**"
            )

        else:
            await ctx.send(
                "The raid did not manage to kill the hamburger within 45 Minutes... He"
                " disappeared!"
            )

        await asyncio.sleep(30)
        await ctx.channel.set_permissions(
            ctx.guild.default_role,
            overwrite=self.deny_sending,
        )
        await self.clear_raid_timer()
        self.boss = None

    @is_god()
    @raid_free()
    @commands.command(hidden=True, brief=_("Starts Astraea' trial"))
    async def goodspawn(self, ctx):
        """[Astraea only] Starts a Trial."""
        await self.set_raid_timer()

        view = JoinView(
            Button(style=ButtonStyle.primary, label="Join the trial!"),
            message=_("You joined the trial."),
            timeout=60 * 15,
        )

        await ctx.send(
            """
In Athena's grace, embrace the light,
Seek trials that soothe, heal the blight.
With kindness as your guiding star,
Illuminate souls from near and far.

**__Champions of compassion, take your stand.__**
Trial Begins in 15 minutes

**Only followers of Astraea may join.**""",
            file=discord.File("assets/other/lyx.webp"),
            view=view,
        )
        if not self.bot.config.bot.is_beta:
            await asyncio.sleep(300)
            await ctx.send("**Astraea and her Ouroboros will be visible in 10 minutes**")
            await asyncio.sleep(300)
            await ctx.send("**Astraea and her Ouroboros will be visible in 5 minutes**")
            await asyncio.sleep(180)
            await ctx.send("**Astraea and her Ouroboros will be visible in 2 minutes**")
            await asyncio.sleep(60)
            await ctx.send("**Astraea and her Ouroboros will be visible in 1 minute**")
            await asyncio.sleep(30)
            await ctx.send("**Astraea and her Ouroboros will be visible in 30 seconds**")
            await asyncio.sleep(20)
            await ctx.send("**Astraea and her Ouroboros will be visible in 10 seconds**")
        else:
            await asyncio.sleep(300)
            await ctx.send("**Astraea's trial will commence in 10 minutes**")
            await asyncio.sleep(300)
            await ctx.send("**Astraea's trial will commence in 5 minutes**")
            await asyncio.sleep(180)
            await ctx.send("**Astraea's trial will commence in 2 minutes**")
            await asyncio.sleep(60)
            await ctx.send("**Astraea's trial will commence in 1 minute**")
            await asyncio.sleep(30)
            await ctx.send("**Astraea's trial will commence in 30 seconds**")
            await asyncio.sleep(20)
            await ctx.send("**Astraea's trial will commence in 10 seconds**")

        view.stop()

        await ctx.send(
            "**Astraea's trial will commence! Fetch participant data... Hang on!**"
        )

        async with self.bot.pool.acquire() as conn:
            raid = []
            for u in view.joined:
                if (
                    not (
                        profile := await conn.fetchrow(
                            'SELECT * FROM profile WHERE "user"=$1;', u.id
                        )
                    )
                    or profile["god"] != "Astraea"
                ):
                    continue
                raid.append(u)

        await ctx.send("**Done getting data!**")

        while len(raid) > 1:
            time = random.choice(["day", "night"])
            if time == "day":
                em = discord.Embed(
                    title="It turns day",
                    description="As the sun's golden rays grace the horizon, a sense of renewal spreads across the "
                                "land. The world awakens from its slumber, bathed in warmth and hope.",
                    colour=0xFFB900,
                )
            else:
                em = discord.Embed(
                    title="It turns night",
                    description="The world embraces the embrace of the night, shrouded in mystery and quietude. The "
                                "stars twinkle like distant promises, and the nocturnal creatures begin their "
                                "whispered symphony.",
                    colour=0xFFB900,
                )
            em.set_thumbnail(url=f"{self.bot.BASE_URL}/image/lyx.png")
            await ctx.send(embed=em)
            await asyncio.sleep(5)
            target = random.choice(raid)
            if time == "day":
                event = random.choice(
                    [
                        {
                            "text": "Extend a Healing Hand",
                            "win": 80,
                            "win_text": "Your compassionate efforts have brought healing and solace. Astraea smiles "
                                        "upon you.",
                            "lose_text": "Despite your intentions, your healing touch falters. Astraea's grace eludes "
                                         "you.",
                        },
                        {
                            "text": "Ease Emotional Burdens",
                            "win": 50,
                            "win_text": "Through your empathetic words, you mend fractured souls. Astraea's favor "
                                        "shines on you.",
                            "lose_text": "Your words fall short, unable to mend the hearts before you. Astraea's "
                                         "blessing slips away.",
                        },
                        {
                            "text": "Kindness in Action",
                            "win": 60,
                            "win_text": "Your selfless actions spread ripples of kindness. Astraea's radiant gaze "
                                        "embraces you.",
                            "lose_text": "Your attempts at kindness don't fully resonate. Astraea's warmth remains "
                                         "distant.",
                        },
                    ]
                )
            else:
                event = random.choice(
                    [
                        {
                            "text": "Guiding Light of Compassion",
                            "win": 30,
                            "win_text": "Amidst the tranquil night, your compassion brings light to dark corners. "
                                        "Astraea's approval graces you.",
                            "lose_text": "Your efforts to bring solace in the night are met with challenges. Astraea's "
                                         "light evades you.",
                        },
                        {
                            "text": "Healing Moon's Embrace",
                            "win": 45,
                            "win_text": "Under the moon's serenity, your healing touch is magnified. Astraea's "
                                        "presence envelops you.",
                            "lose_text": "Your attempts to heal are hindered by unseen forces. Astraea's touch remains "
                                         "elusive.",
                        },
                        {
                            "text": "Celestial Blessing of Serenity",
                            "win": 20,
                            "win_text": "As the stars align in your favor, Astraea's serene blessings envelop you. A "
                                        "tranquil aura emanates from your being, soothing all around.",
                            "lose_text": "Despite your efforts to channel the cosmos, Astraea's tranquility eludes "
                                         "you, leaving only fleeting traces of its presence.",
                        },
                        {
                            "text": "Stellar Harmonies of Renewal",
                            "win": 20,
                            "win_text": "In harmony with the celestial melodies, your actions resonate with Astraea's "
                                        "essence. The stars themselves seem to sing your praises, infusing the air "
                                        "with renewal.",
                            "lose_text": "The cosmic harmonies remain elusive, and your attempts to align with "
                                         "Astraea's melody falter, leaving a sense of missed opportunity in the "
                                         "night's chorus.",
                        }
                    ]
                )
            does_win = event["win"] >= random.randint(1, 100)
            if does_win:
                text = event["win_text"]
            else:
                text = event["lose_text"]
                raid.remove(target)
            em = discord.Embed(
                title=event["text"],
                description=text,
                colour=0xFFB900,
            )
            em.set_author(name=f"{target}", icon_url=target.display_avatar.url)
            em.set_footer(text=f"{len(raid)} followers remain")
            em.set_thumbnail(url=f"{self.bot.BASE_URL}/image/lyx.png")
            await ctx.send(embed=em)
            await asyncio.sleep(5)

        winner = raid[0]
        await ctx.send(
            f"In the divine radiance of Astraea, {winner.mention} ascends to the cosmic realm. Guided by the "
            f"goddess's embrace, they uncover a celestial treasure—an enigmatic, legendary crate adorned with "
            f"stardust among the constellations."
        )
        async with self.bot.pool.acquire() as conn:
            await conn.execute(
                'UPDATE profile SET "crates_legendary"="crates_legendary"+1 WHERE "user"=$1;',
                winner.id,
            )
        await self.clear_raid_timer()

    @is_god()
    @raid_free()
    @commands.command(hidden=True, brief=_("Start a Drakath raid"))
    async def chaosspawn(self, ctx):
        """[Drakath only] Starts a raid."""
        await self.set_raid_timer()

        boss_hp = random.randint(500, 1000)

        view = JoinView(
            Button(style=ButtonStyle.primary, label="Join the raid!"),
            message=_("You joined the raid."),
            timeout=60 * 15,
        )

        em = discord.Embed(
            title="Raid the Void",
            description=f"""
In Drakath's name, unleash the storm,
Raiders of chaos, in shadows swarm.
No order, no restraint, just untamed glee,
Drakath's chaos shall set us free.

Eclipse the Void Conqueror has {boss_hp} HP and will be vulnerable in 15 Minutes

**Only followers of Drakath may join.**""",
            color=0xFFB900,
        )
        em.set_image(url=f"https://i.imgur.com/YoszTlc.png")
        await ctx.send(embed=em, view=view)

        if not self.bot.config.bot.is_beta:
            await asyncio.sleep(300)
            await ctx.send("**The raid on the void will start in 10 minutes**")
            await asyncio.sleep(300)
            await ctx.send("**The raid on the void will start in 5 minutes**")
            await asyncio.sleep(180)
            await ctx.send("**The raid on the void will start in 2 minutes**")
            await asyncio.sleep(60)
            await ctx.send("**The raid on the void will start in 1 minute**")
            await asyncio.sleep(30)
            await ctx.send("**The raid on the void will start in 30 seconds**")
            await asyncio.sleep(20)
            await ctx.send("**The raid on the void will start in 10 seconds**")
            await asyncio.sleep(10)
        else:
            await asyncio.sleep(300)
            await ctx.send("**The raid on the void will start in 10 minutes**")
            await asyncio.sleep(300)
            await ctx.send("**The raid on the void will start in 5 minutes**")
            await asyncio.sleep(180)
            await ctx.send("**The raid on the void will start in 2 minutes**")
            await asyncio.sleep(60)
            await ctx.send("**The raid on the void will start in 1 minute**")
            await asyncio.sleep(30)
            await ctx.send("**The raid on the void will start in 30 seconds**")
            await asyncio.sleep(20)
            await ctx.send("**The raid on the void will start in 10 seconds**")

        view.stop()

        await ctx.send(
            "**The raid on the facility started! Fetching participant data... Hang on!**"
        )

        async with self.bot.pool.acquire() as conn:
            raid = {}
            for u in view.joined:
                if (
                    not (
                        profile := await conn.fetchrow(
                            'SELECT * FROM profile WHERE "user"=$1;', u.id
                        )
                    )
                    or profile["god"] != "Drakath"
                ):
                    continue
                raid[u] = 250

        await ctx.send("**Done getting data!**")

        start = datetime.datetime.utcnow()

        while (
            boss_hp > 0
            and len(raid) > 0
            and datetime.datetime.utcnow() < start + datetime.timedelta(minutes=45)
        ):
            target = random.choice(list(raid.keys()))
            dmg = random.randint(100, 300)
            raid[target] -= dmg
            if raid[target] > 0:
                em = discord.Embed(
                    title="Eclipse attacks!",
                    description=f"{target} now has {raid[target]} HP!",
                    colour=0xFFB900,
                )
            else:
                em = discord.Embed(
                    title="Eclipse hits critical!",
                    description=f"{target} died!",
                    colour=0xFFB900,
                )
            em.add_field(name="Damage", value=dmg)
            em.set_author(name=str(target), icon_url=target.display_avatar.url)
            em.set_thumbnail(url=f"https://i.imgur.com/YS4A6R7.png")
            await ctx.send(embed=em)
            if raid[target] <= 0:
                del raid[target]
                if len(raid) == 0:
                    break

            # Russian lemon powerup restores your hp by 100
            if random.randint(1, 5) == 1:
                await asyncio.sleep(4)
                target = random.choice(list(raid.keys()))
                raid[target] += 100
                em = discord.Embed(
                    title=f"{target} uses Chaos Restore!",
                    description=f"It's super effective!\n{target} now has {raid[target]} HP!",
                    colour=0xFFB900,
                )
                em.set_author(name=str(target), icon_url=target.display_avatar.url)
                em.set_thumbnail(url=f"https://i.imgur.com/md5dWFk.png")
                await ctx.send(embed=em)

            # NIC traps might explode
            if random.randint(1, 5) == 1:
                await asyncio.sleep(4)
                if len(raid) >= 3:
                    targets = random.sample(list(raid.keys()), 3)
                else:
                    targets = list(raid.keys())
                for target in targets:
                    raid[target] -= 100
                    if raid[target] <= 0:
                        del raid[target]
                em = discord.Embed(
                    title="Eclipse prepares a void pulse!",
                    description=f"It's super effective!\n{', '.join(str(u) for u in targets)} take 100 damage!",
                    colour=0xFFB900,
                )
                em.set_thumbnail(url=f"https://i.imgur.com/lDqNHua.png")
                await ctx.send(embed=em)

            # Sausages do 25dmg and a 10% crit of 75-100
            dmg_to_take = sum(
                25 if random.randint(1, 10) != 10 else random.randint(75, 100)
                for u in raid
            )
            boss_hp -= dmg_to_take
            await asyncio.sleep(4)
            em = discord.Embed(
                title="The power of Drakath's Followers attacks Eclipse!", colour=0xFF5C00
            )
            em.set_thumbnail(url=f"https://i.imgur.com/kf3zcLs.png")
            em.add_field(name="Damage", value=dmg_to_take)
            if boss_hp > 0:
                em.add_field(name="HP left", value=boss_hp)
            else:
                em.add_field(name="HP left", value="Dead!")
            await ctx.send(embed=em)
            await asyncio.sleep(4)

        if boss_hp > 1 and len(raid) > 0:
            # Timed out
            em = discord.Embed(
                title="Defeat",
                description="As Drakath's malevolent laughter echoes through the shattered realm, his followers stand "
                            "defeated before the overwhelming might of their vanquished foe, a stark reminder of "
                            "chaos's unyielding and capricious nature.",
                color=0xFFB900,
            )
            em.set_image(url=f"https://i.imgur.com/s5tvHMd.png")
            await ctx.send(embed=em)
        elif len(raid) == 0:
            em = discord.Embed(
                title="Defeat",
                description="Amidst the smoldering ruins and the mocking whispers of the chaotic winds, Drakath's "
                            "followers find themselves humbled by the boss's insurmountable power, their hopes dashed "
                            "like shattered illusions in the wake of their failure.",
                color=0xFFB900,
            )
            em.set_image(url=f"https://i.imgur.com/UpWW3fF.png")
            await ctx.send(embed=em)
        else:
            winner = random.choice(list(raid.keys()))
            async with self.bot.pool.acquire() as conn:
                await conn.execute(
                    'UPDATE profile SET "crates_legendary"="crates_legendary"+1 WHERE "user"=$1;',
                    winner.id,
                )
            em = discord.Embed(
                title="Win!",
                description=f"The forces aligned with Drakath have triumphed over Eclipse, wresting victory from the "
                            f"clutches of chaos itself!\n{winner.mention} emerges as a true champion of anarchy, "
                            f"earning a legendary crate from Drakath as a token of recognition for their unrivaled "
                            f"prowess!",
                color=0xFFB900,
            )
            em.set_image(url=f"https://i.imgur.com/U1Of4tz.png")
            await ctx.send(embed=em)
        await self.clear_raid_timer()

    @is_god()
    @raid_free()
    @commands.command(hidden=True, brief=_("Start a Kirby raid"))
    async def kirbycultspawn(self, ctx, hp: IntGreaterThan(0)):
        """[Kirby only] Starts a raid."""
        await self.set_raid_timer()
        self.boss = {"hp": hp, "min_dmg": 200, "max_dmg": 300}

        view = JoinView(
            Button(style=ButtonStyle.primary, label="Join the raid!"),
            message=_("You joined the raid."),
            timeout=60 * 15,
        )

        em = discord.Embed(
            title="Dark Mind attacks Dream Land",
            description=f"""
**A great curse has fallen upon Dream Land! Dark Mind is trying to conquer Dream Land and absorb it to the Mirror World! Join forces and defend Dream Land!**

This boss has {self.boss['hp']} HP and will be vulnerable in 15 Minutes

**Only followers of Kirby may join.**""",
            color=0xFFB900,
        )
        em.set_image(url=f"{self.bot.BASE_URL}/image/dark_mind.png")
        await ctx.send(embed=em, view=view)

        if not self.bot.config.bot.is_beta:
            await asyncio.sleep(300)
            await ctx.send("**The attack on Dream Land will start in 10 minutes**")
            await asyncio.sleep(300)
            await ctx.send("**The attack on Dream Land will start in 5 minutes**")
            await asyncio.sleep(180)
            await ctx.send("**The attack on Dream Land will start in 2 minutes**")
            await asyncio.sleep(60)
            await ctx.send("**The attack on Dream Land will start in 1 minute**")
            await asyncio.sleep(30)
            await ctx.send("**The attack on Dream Land will start in 30 seconds**")
            await asyncio.sleep(20)
            await ctx.send("**The attack on Dream Land will start in 10 seconds**")
            await asyncio.sleep(10)
        else:
            await asyncio.sleep(60)

        view.stop()

        await ctx.send(
            "**The attack on Dream Land started! Fetching participant data... Hang on!**"
        )

        async with self.bot.pool.acquire() as conn:
            raid = {}
            for u in view.joined:
                if (
                    not (
                        profile := await conn.fetchrow(
                            'SELECT * FROM profile WHERE "user"=$1;', u.id
                        )
                    )
                    or profile["god"] != "Kirby"
                ):
                    continue
                try:
                    dmg, deff = await self.bot.get_raidstats(u, god="Kirby", conn=conn)
                except ValueError:
                    continue
                raid[u] = {"hp": 250, "armor": deff, "damage": dmg}

        await ctx.send("**Done getting data!**")

        start = datetime.datetime.utcnow()

        while (
            self.boss["hp"] > 0
            and len(raid) > 0
            and datetime.datetime.utcnow() < start + datetime.timedelta(minutes=10)
        ):
            target = random.choice(list(raid.keys()))
            dmg = random.randint(self.boss["min_dmg"], self.boss["max_dmg"])
            dmg = self.getfinaldmg(dmg, raid[target]["armor"])
            raid[target]["hp"] -= dmg
            if raid[target]["hp"] > 0:
                em = discord.Embed(
                    title="Dark Mind attacked!",
                    description=f"{target} now has {raid[target]['hp']} HP!",
                    colour=0xFFB900,
                )
            else:
                em = discord.Embed(
                    title="Dark Mind attacked!",
                    description=f"{target} died!",
                    colour=0xFFB900,
                )
            em.add_field(name="Theoretical Damage", value=dmg + raid[target]["armor"])
            em.add_field(name="Shield", value=raid[target]["armor"])
            em.add_field(name="Effective Damage", value=dmg)
            em.set_author(name=str(target), icon_url=target.display_avatar.url)
            em.set_thumbnail(url=f"{self.bot.BASE_URL}/image/dark_mind.png")
            await ctx.send(embed=em)
            if raid[target]["hp"] <= 0:
                del raid[target]
            dmg_to_take = sum(i["damage"] for i in raid.values())
            self.boss["hp"] -= dmg_to_take
            await asyncio.sleep(4)
            em = discord.Embed(title="The raiders attacked Dark Mind!", colour=0xFF5C00)
            em.set_thumbnail(url=f"{self.bot.BASE_URL}/image/kirby_raiders.png")
            em.add_field(name="Damage", value=dmg_to_take)
            if self.boss["hp"] > 0:
                em.add_field(name="HP left", value=self.boss["hp"])
            else:
                em.add_field(name="HP left", value="Dead!")
            await ctx.send(embed=em)
            await asyncio.sleep(4)

        if len(raid) == 0:
            em = discord.Embed(
                title="Defeat!",
                description="Dark Mind was too strong! You cannot stop him from conquering Dream Land as he ushers in a dark period of terror and tyranny!",
                color=0xFFB900,
            )
            em.set_image(url=f"{self.bot.BASE_URL}/image/kirby_loss.png")
            await self.clear_raid_timer()
            return await ctx.send(embed=em)
        elif self.boss["hp"] > 0:
            em = discord.Embed(
                title="Timed out!",
                description="You took too long! The mirror world has successfully absorbed Dream Land and it is lost forever.",
                color=0xFFB900,
            )
            em.set_image(url=f"{self.bot.BASE_URL}/image/kirby_timeout.png")
            await self.clear_raid_timer()
            return await ctx.send(embed=em)
        em = discord.Embed(
            title="Win!",
            description="Hooray! Dream Land is saved!",
            color=0xFFB900,
        )
        em.set_image(url=f"{self.bot.BASE_URL}/image/kirby_win.png")
        await ctx.send(embed=em)
        await asyncio.sleep(5)
        em = discord.Embed(
            title="Dark Mind returns!",
            description="Oh no! Dark Mind is back in his final form, stronger than ever before! Defeat him once and for all to protect Dream Land!",
            color=0xFFB900,
        )
        em.set_image(url=f"{self.bot.BASE_URL}/image/kirby_return.png")
        await ctx.send(embed=em)
        await asyncio.sleep(5)

        self.boss = {"hp": hp, "min_dmg": 300, "max_dmg": 400}
        while self.boss["hp"] > 0 and len(raid) > 0:
            target = random.choice(list(raid.keys()))
            dmg = random.randint(self.boss["min_dmg"], self.boss["max_dmg"])
            dmg = self.getfinaldmg(dmg, raid[target]["armor"])
            raid[target]["hp"] -= dmg
            if raid[target]["hp"] > 0:
                em = discord.Embed(
                    title="Dark Mind attacked!",
                    description=f"{target} now has {raid[target]['hp']} HP!",
                    colour=0xFFB900,
                )
            else:
                em = discord.Embed(
                    title="Dark Mind attacked!",
                    description=f"{target} died!",
                    colour=0xFFB900,
                )
            em.add_field(name="Theoretical Damage", value=dmg + raid[target]["armor"])
            em.add_field(name="Shield", value=raid[target]["armor"])
            em.add_field(name="Effective Damage", value=dmg)
            em.set_author(name=str(target), icon_url=target.display_avatar.url)
            em.set_thumbnail(url=f"{self.bot.BASE_URL}/image/dark_mind_final.png")
            await ctx.send(embed=em)
            if raid[target]["hp"] <= 0:
                del raid[target]
            dmg_to_take = sum(i["damage"] for i in raid.values())
            self.boss["hp"] -= dmg_to_take
            await asyncio.sleep(4)
            em = discord.Embed(title="The raiders attacked Dark Mind!", colour=0xFF5C00)
            em.set_thumbnail(url=f"{self.bot.BASE_URL}/image/kirby_raiders.png")
            em.add_field(name="Damage", value=dmg_to_take)
            if self.boss["hp"] > 0:
                em.add_field(name="HP left", value=self.boss["hp"])
            else:
                em.add_field(name="HP left", value="Dead!")
            await ctx.send(embed=em)
            await asyncio.sleep(4)

        if self.boss["hp"] > 0:
            em = discord.Embed(
                title="Defeat!",
                description="Dark Mind was too strong! You cannot stop him from conquering Dream Land as he ushers in a dark period of terror and tyranny!",
                color=0xFFB900,
            )
            em.set_image(url=f"{self.bot.BASE_URL}/image/kirby_loss.png")
            await self.clear_raid_timer()
            return await ctx.send(embed=em)
        winner = random.choice(list(raid.keys()))
        em = discord.Embed(
            title="Win!",
            description=f"Hooray! Dark Mind is defeated and his dream of conquering Dream Land is shattered. You return back to Dream Land to Cappy Town where you are met with a huge celebration! The Mayor gives {winner.mention} a Legendary Crate for your bravery!\n**Gave $10000 to each survivor**",
            color=0xFFB900,
        )
        em.set_image(url=f"{self.bot.BASE_URL}/image/kirby_final_win.png")
        await ctx.send(embed=em)

        users = [u.id for u in raid]

        async with self.bot.pool.acquire() as conn:
            await conn.execute(
                'UPDATE profile SET "crates_legendary"="crates_legendary"+1 WHERE "user"=$1;',
                winner.id,
            )
            await conn.execute(
                'UPDATE profile SET "money"="money"+$1 WHERE "user"=ANY($2);',
                10000,
                users,
            )
        await self.clear_raid_timer()

    @is_god()
    @raid_free()
    @commands.command(hidden=True, brief=_("Start a Jesus raid"))
    async def jesusspawn(self, ctx, hp: IntGreaterThan(0)):
        """[Jesus only] Starts a raid."""
        await self.set_raid_timer()
        self.boss = {"hp": hp, "min_dmg": 100, "max_dmg": 500}
        await ctx.channel.set_permissions(
            ctx.guild.default_role,
            overwrite=self.read_only,
        )

        view = JoinView(
            Button(style=ButtonStyle.primary, label="Join the raid!"),
            message=_("You joined the raid."),
            timeout=60 * 15,
        )

        await ctx.send(
            f"""
**Atheistus the Tormentor has returned to earth to punish humanity for their belief.**

This boss has {self.boss['hp']} HP and has high-end loot!
Atheistus will be vulnerable in 15 Minutes

**Only followers of Jesus may join.**""",
            file=discord.File("assets/other/atheistus.webp"),
            view=view,
        )

        if not self.bot.config.bot.is_beta:
            await asyncio.sleep(300)
            await ctx.send("**Atheistus will be vulnerable in 10 minutes**")
            await asyncio.sleep(300)
            await ctx.send("**Atheistus will be vulnerable in 5 minutes**")
            await asyncio.sleep(180)
            await ctx.send("**Atheistus will be vulnerable in 2 minutes**")
            await asyncio.sleep(60)
            await ctx.send("**Atheistus will be vulnerable in 1 minute**")
            await asyncio.sleep(30)
            await ctx.send("**Atheistus will be vulnerable in 30 seconds**")
            await asyncio.sleep(20)
            await ctx.send("**Atheistus will be vulnerable in 10 seconds**")
            await asyncio.sleep(10)
        else:
            await asyncio.sleep(60)

        view.stop()

        await ctx.send(
            "**Atheistus is vulnerable! Fetching participant data... Hang on!**"
        )

        async with self.bot.pool.acquire() as conn:
            raid = {}
            for u in view.joined:
                if (
                    not (
                        profile := await conn.fetchrow(
                            'SELECT * FROM profile WHERE "user"=$1;', u.id
                        )
                    )
                    or profile["god"] != "Jesus"
                ):
                    continue
                try:
                    dmg, deff = await self.bot.get_raidstats(u, god="Jesus", conn=conn)
                except ValueError:
                    continue
                raid[u] = {"hp": 250, "armor": deff, "damage": dmg}

        await ctx.send("**Done getting data!**")

        start = datetime.datetime.utcnow()

        while (
            self.boss["hp"] > 0
            and len(raid) > 0
            and datetime.datetime.utcnow() < start + datetime.timedelta(minutes=45)
        ):
            target = random.choice(list(raid.keys()))
            dmg = random.randint(self.boss["min_dmg"], self.boss["max_dmg"])
            dmg = self.getfinaldmg(dmg, raid[target]["armor"])
            raid[target]["hp"] -= dmg
            if raid[target]["hp"] > 0:
                em = discord.Embed(
                    title="Atheistus attacked!",
                    description=f"{target} now has {raid[target]['hp']} HP!",
                    colour=0xFFB900,
                )
            else:
                em = discord.Embed(
                    title="Atheistus attacked!",
                    description=f"{target} died!",
                    colour=0xFFB900,
                )
            em.add_field(name="Theoretical Damage", value=dmg + raid[target]["armor"])
            em.add_field(name="Shield", value=raid[target]["armor"])
            em.add_field(name="Effective Damage", value=dmg)
            em.set_author(name=str(target), icon_url=target.display_avatar.url)
            em.set_thumbnail(url=f"{self.bot.BASE_URL}/atheistus.jpg")
            await ctx.send(embed=em)
            if raid[target]["hp"] <= 0:
                del raid[target]
            dmg_to_take = sum(i["damage"] for i in raid.values())
            self.boss["hp"] -= dmg_to_take
            await asyncio.sleep(4)
            em = discord.Embed(title="The raid attacked Atheistus!", colour=0xFF5C00)
            em.set_thumbnail(url=f"{self.bot.BASE_URL}/knight.jpg")
            em.add_field(name="Damage", value=dmg_to_take)
            if self.boss["hp"] > 0:
                em.add_field(name="HP left", value=self.boss["hp"])
            else:
                em.add_field(name="HP left", value="Dead!")
            await ctx.send(embed=em)
            await asyncio.sleep(4)

        if len(raid) == 0:
            await ctx.send("The raid was all wiped!")
        elif self.boss["hp"] < 1:
            await ctx.channel.set_permissions(
                ctx.guild.default_role,
                overwrite=self.allow_sending,
            )
            highest_bid = [
                356_091_260_429_402_122,
                0,
            ]  # userid, amount

            def check(msg):
                if (
                    msg.channel.id != ctx.channel.id
                    or (not msg.content.isdigit())
                    or (msg.author not in raid)
                ):
                    return False
                if not (int(msg.content) > highest_bid[1]):
                    return False
                if (
                    msg.author.id == highest_bid[0]
                ):  # don't allow a player to outbid themselves
                    return False
                return True

            page = commands.Paginator()
            for u in list(raid.keys()):
                page.add_line(u.mention)
            page.add_line(
                "The raid killed the boss!\nHe dropped a"
                f" {self.bot.cogs['Crates'].emotes.legendary} Legendary Crate!\nThe highest"
                " bid for it wins <:roosip:505447694408482846>\nSimply type how much"
                " you bid!"
            )
            for p in page.pages:
                await ctx.send(p[4:-4])

            while True:
                try:
                    msg = await self.bot.wait_for("message", timeout=60, check=check)
                except asyncio.TimeoutError:
                    break
                bid = int(msg.content)
                money = await self.bot.pool.fetchval(
                    'SELECT money FROM profile WHERE "user"=$1;', msg.author.id
                )
                if money and money >= bid:
                    highest_bid = [msg.author.id, bid]
                    await ctx.send(f"{msg.author.mention} bids **${msg.content}**!")
            msg = await ctx.send(
                f"Auction done! Winner is <@{highest_bid[0]}> with"
                f" **${highest_bid[1]}**!\nGiving Legendary Crate..."
            )
            money = await self.bot.pool.fetchval(
                'SELECT money FROM profile WHERE "user"=$1;', highest_bid[0]
            )
            if money >= highest_bid[1]:
                async with self.bot.pool.acquire() as conn:
                    await conn.execute(
                        'UPDATE profile SET "money"="money"-$1,'
                        ' "crates_legendary"="crates_legendary"+1 WHERE "user"=$2;',
                        highest_bid[1],
                        highest_bid[0],
                    )
                    await self.bot.log_transaction(
                        ctx,
                        from_=highest_bid[0],
                        to=2,
                        subject="money",
                        data={"Amount": highest_bid[1]},
                        conn=conn,
                    )
                await msg.edit(content=f"{msg.content} Done!")
            else:
                await ctx.send(
                    f"<@{highest_bid[0]}> spent the money in the meantime... Meh!"
                    " Noone gets it then, pah!\nThis incident has been reported and"
                    " they will get banned if it happens again. Cheers!"
                )

            cash = int(hp / 4 / len(raid))  # what da hood gets per survivor
            users = [u.id for u in raid]
            await self.bot.pool.execute(
                'UPDATE profile SET money=money+$1 WHERE "user"=ANY($2);',
                cash,
                users,
            )
            await ctx.send(
                f"**Gave ${cash} of Atheistus' ${int(hp / 4)} drop to all survivors!"
                " Thanks to you, the world can live in peace and love again.**"
            )

        else:
            await ctx.send(
                "The raid did not manage to kill Atheistus within 45 Minutes... He"
                " disappeared!"
            )

        await asyncio.sleep(30)
        await ctx.channel.set_permissions(
            ctx.guild.default_role,
            overwrite=self.deny_sending,
        )
        await self.clear_raid_timer()
        self.boss = None

    def getpriceto(self, level: float):
        return sum(i * 25000 for i in range(1, int(level * 10) - 9))

    @commands.group(invoke_without_command=True, brief=_("Increase your raidstats"))
    @locale_doc
    async def increase(self, ctx):
        _(
            """Upgrade your raid damage or defense multiplier. These will affect your performance in raids and raidbattles."""
        )
        await ctx.send(
            _(
                "Use `{prefix}increase damage/defense` to upgrade your raid"
                " damage/defense multiplier by 10%."
            ).format(prefix=ctx.clean_prefix)
        )

    @user_cooldown(60, identifier="increase")
    @has_char()
    @increase.command(brief=_("Upgrade your raid damage"))
    @locale_doc
    async def damage(self, ctx):
        _("""Increase your raid damage.""")
        newlvl = ctx.character_data["atkmultiply"] + Decimal("0.1")
        price = self.getpriceto(newlvl)
        if ctx.character_data["money"] < price:
            return await ctx.send(
                _(
                    "Upgrading your weapon attack raid multiplier to {newlvl} costs"
                    " **${price}**, you are too poor."
                ).format(newlvl=newlvl, price=price)
            )
        if not await ctx.confirm(
            _(
                "Upgrading your weapon attack raid multiplier to {newlvl} costs"
                " **${price}**, proceed?"
            ).format(newlvl=newlvl, price=price)
        ):
            return
        async with self.bot.pool.acquire() as conn:
            if not await self.bot.has_money(ctx.author, price, conn=conn):
                return await ctx.send(
                    _(
                        "Upgrading your weapon attack raid multiplier to {newlvl} costs"
                        " **${price}**, you are too poor."
                    ).format(newlvl=newlvl, price=price)
                )
            await conn.execute(
                'UPDATE profile SET "atkmultiply"=$1, "money"="money"-$2 WHERE'
                ' "user"=$3;',
                newlvl,
                price,
                ctx.author.id,
            )
            await self.bot.log_transaction(
                ctx,
                from_=ctx.author.id,
                to=2,
                subject="money",
                data={"Amount": price},
                conn=conn,
            )
        await ctx.send(
            _(
                "You upgraded your weapon attack raid multiplier to {newlvl} for"
                " **${price}**."
            ).format(newlvl=newlvl, price=price)
        )

    @user_cooldown(60, identifier="increase")
    @has_char()
    @increase.command(brief=_("Upgrade your raid defense"))
    @locale_doc
    async def defense(self, ctx):
        _("""Increase your raid defense.""")
        newlvl = ctx.character_data["defmultiply"] + Decimal("0.1")
        price = self.getpriceto(newlvl)
        if ctx.character_data["money"] < price:
            return await ctx.send(
                _(
                    "Upgrading your shield defense raid multiplier to {newlvl} costs"
                    " **${price}**, you are too poor."
                ).format(newlvl=newlvl, price=price)
            )
        if not await ctx.confirm(
            _(
                "Upgrading your shield defense raid multiplier to {newlvl} costs"
                " **${price}**, proceed?"
            ).format(newlvl=newlvl, price=price)
        ):
            return
        async with self.bot.pool.acquire() as conn:
            if not await self.bot.has_money(ctx.author, price, conn=conn):
                return await ctx.send(
                    _(
                        "Upgrading your shield defense raid multiplier to {newlvl}"
                        " costs **${price}**, you are too poor."
                    ).format(newlvl=newlvl, price=price)
                )
            await conn.execute(
                'UPDATE profile SET "defmultiply"=$1, "money"="money"-$2 WHERE'
                ' "user"=$3;',
                newlvl,
                price,
                ctx.author.id,
            )
            await self.bot.log_transaction(
                ctx,
                from_=ctx.author.id,
                to=2,
                subject="money",
                data={"Amount": price},
                conn=conn,
            )
        await ctx.send(
            _(
                "You upgraded your shield defense raid multiplier to {newlvl} for"
                " **${price}**."
            ).format(newlvl=newlvl, price=price)
        )

    @has_char()
    @commands.command(brief=_("View your raid stats"))
    @locale_doc
    async def raidstats(self, ctx):
        _(
            """View your raidstats. These will affect your performance in raids and raidbattles."""
        )
        atk = ctx.character_data["atkmultiply"]
        deff = ctx.character_data["defmultiply"]
        atkp = self.getpriceto(atk + Decimal("0.1"))
        deffp = self.getpriceto(deff + Decimal("0.1"))
        classes = [class_from_string(c) for c in ctx.character_data["class"]]
        for c in classes:
            if c and c.in_class_line(Raider):
                tier = c.class_grade()
                atk += Decimal("0.1") * tier
                deff += Decimal("0.1") * tier
        if buildings := await self.bot.get_city_buildings(ctx.character_data["guild"]):
            atk += Decimal("0.1") * buildings["raid_building"]
            deff += Decimal("0.1") * buildings["raid_building"]
        await ctx.send(
            _(
                "**{author}'s raid multipliers**\nDamage Multiplier: x{atk} (Upgrading:"
                " ${atkp})\nDefense Multiplier: x{deff} (Upgrading: ${deffp})"
            ).format(
                author=ctx.author.mention, atk=atk, atkp=atkp, deff=deff, deffp=deffp
            )
        )

    @commands.command(brief=_("Did somebody say Raid?"))
    @locale_doc
    async def raid(self, ctx):
        _("""Informs you about joining raids.""")
        await ctx.send(
            _(
                "Did you ever want to join together with other players to defeat the"
                " dragon that roams this land? Raids got you covered!\nJoin the support"
                " server (`{prefix}support`) for more information."
            ).format(prefix=ctx.clean_prefix)
        )


async def setup(bot):
    await bot.add_cog(Raid(bot))
