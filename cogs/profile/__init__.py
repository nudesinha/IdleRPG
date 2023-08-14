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

import discord
import io

from aiohttp import ContentTypeError
from discord.ext import commands

from classes.badges import Badge
from classes.bot import Bot
from classes.classes import from_string as class_from_string
from classes.context import Context
from classes.converters import IntFromTo, MemberWithCharacter, UserWithCharacter
from classes.items import ALL_ITEM_TYPES, ItemType
from cogs.adventure import ADVENTURE_NAMES
from cogs.help import chunks
from cogs.shard_communication import user_on_cooldown as user_cooldown
from utils import checks, colors
from utils import misc as rpgtools
from utils.i18n import _, locale_doc


class Profile(commands.Cog):
    def __init__(self, bot: Bot) -> None:
        self.bot = bot

    @checks.has_no_char()
    @user_cooldown(3600)
    @commands.command(aliases=["new", "c", "start"], brief=_("Create a new character"))
    @locale_doc
    async def create(self, ctx, *, name: str = None):
        _(
            """`[name]` - The name to give your character; will be interactive if not given

            Create a new character and start playing IdleRPG.

            By creating a character, you agree to the [bot rules](https://wiki.idlerpg.xyz/index.php?title=Rules#botrules).
            No idea where to go from here? Check out our [tutorial](https://idlerpg.xyz/tutorial/).
            If you still have questions afterward, feel free to ask us on the official [support server](https://support.idlerpg.xyz/).

            (This command has a cooldown of 1 hour.)"""
        )
        if not name:
            await ctx.send(
                _(
                    """\
What shall your character's name be? (Minimum 3 Characters, Maximum 20)

**Please note that with the creation of a character, you agree to these rules:**
1) Only up to two characters per individual
2) No abusing or benefiting from bugs or exploits
3) Be friendly and kind to other players
4) Trading in-game content for anything outside of the game is prohibited

IdleRPG is a global bot, your characters are valid everywhere"""
                )
            )

            def mycheck(amsg):
                return amsg.author == ctx.author and amsg.channel == ctx.channel

            try:
                name = await self.bot.wait_for("message", timeout=60, check=mycheck)
            except asyncio.TimeoutError:
                await self.bot.reset_cooldown(ctx)
                return await ctx.send(_("Timeout expired. Please retry!"))
            name = name.content
        else:
            if not await ctx.confirm(
                    _(
                        """\
**Please note that with the creation of a character, you agree to these rules:**
1) Only up to two characters per individual
2) No abusing or benefiting from bugs or exploits
3) Be friendly and kind to other players
4) Trading in-game items or currency for real money or items directly comparable to currency is forbidden

IdleRPG is a global bot, your characters are valid everywhere"""
                    )
            ):
                return await ctx.send(_("Creation of your character cancelled."))
        if len(name) > 2 and len(name) < 21:
            if "`" in name:
                return await ctx.send(
                    _(
                        "Illegal character (`) found in the name. Please try again and"
                        " choose another name."
                    )
                )

            async with self.bot.pool.acquire() as conn:
                await conn.execute(
                    "INSERT INTO profile VALUES ($1, $2, $3, $4);",
                    ctx.author.id,
                    name,
                    100,
                    0,
                )
                await self.bot.create_item(
                    name=_("Starter Sword"),
                    value=0,
                    type_="Sword",
                    damage=3.0,
                    armor=0.0,
                    owner=ctx.author,
                    hand="any",
                    equipped=True,
                    conn=conn,
                )
                await self.bot.create_item(
                    name=_("Starter Shield"),
                    value=0,
                    type_="Shield",
                    damage=0.0,
                    armor=3.0,
                    owner=ctx.author,
                    hand="left",
                    equipped=True,
                    conn=conn,
                )
                await self.bot.log_transaction(
                    ctx,
                    from_=1,
                    to=ctx.author.id,
                    subject="money",
                    data={"Amount": 100},
                    conn=conn,
                )
            await ctx.send(
                _(
                    "Successfully added your character **{name}**! Now use"
                    " `{prefix}profile` to view your character!"
                ).format(name=name, prefix=ctx.clean_prefix)
            )
        elif len(name) < 3 or len(name) > 20:
            await ctx.send(
                _("Character names must be at least 3 characters and up to 20.")
            )
            await self.bot.reset_cooldown(ctx)

    @commands.command(aliases=["me", "p"], brief=_("View someone's profile"))
    @locale_doc
    async def profile(self, ctx, *, person: discord.User = None):
        _(
            """`[person]` - The person whose profile to view; defaults to oneself

            View someone's profile. This will send an image.
            For an explanation what all the fields mean, see [this picture](https://wiki.idlerpg.xyz/images/3/35/Profile_explained.png)"""
        )
        person = person or ctx.author
        targetid = person.id

        async with self.bot.pool.acquire() as conn:
            profile = await conn.fetchrow(
                'SELECT p.*, g.name AS guild_name FROM profile p LEFT JOIN guild g ON (g."id"=p."guild") WHERE "user"=$1;',
                targetid,
            )

            if not profile:
                return await ctx.send(
                    _("**{person}** does not have a character.").format(person=person)
                )

            items = await self.bot.get_equipped_items_for(targetid, conn=conn)
            mission = await self.bot.get_adventure(targetid)

        right_hand = None
        left_hand = None

        any_count = sum(1 for i in items if i["hand"] == "any")
        if len(items) == 2 and any_count == 1 and items[0]["hand"] == "any":
            items = [items[1], items[0]]

        for i in items:
            stat = f"{int(i['damage'] + i['armor'])}"
            if i["hand"] == "both":
                right_hand = (i["type"], i["name"], stat)
            elif i["hand"] == "left":
                left_hand = (i["type"], i["name"], stat)
            elif i["hand"] == "right":
                right_hand = (i["type"], i["name"], stat)
            elif i["hand"] == "any":
                if right_hand is None:
                    right_hand = (i["type"], i["name"], stat)
                else:
                    left_hand = (i["type"], i["name"], stat)

        color = profile["colour"]
        color = [color["red"], color["green"], color["blue"], color["alpha"]]
        embed_color = discord.Colour.from_rgb(color[0], color[1], color[2])
        classes = [class_from_string(c) for c in profile["class"]]
        icons = [c.get_class_line_name().lower() if c else "none" for c in classes]

        guild_rank = None if not profile["guild"] else profile["guildrank"]

        marriage = (
            await rpgtools.lookup(self.bot, profile["marriage"], return_none=True)
            if profile["marriage"]
            else None
        )

        if mission:
            adventure_name = ADVENTURE_NAMES[mission[0]]
            adventure_time = f"{mission[1]}" if not mission[2] else _("Finished")
        else:
            adventure_name = None
            adventure_time = None

        badge_val = Badge.from_db(profile["badges"])
        if badge_val:
            badges = badge_val.to_items_lowercase()
        else:
            badges = []

        async with self.bot.trusted_session.post(
                f"{self.bot.config.external.okapi_url}/api/genprofile",
                json={
                    "name": profile["name"],
                    "color": color,
                    "image": profile["background"],
                    "race": profile["race"],
                    "classes": profile["class"],
                    "class_icons": icons,
                    "left_hand_item": left_hand,
                    "right_hand_item": right_hand,
                    "level": f"{rpgtools.xptolevel(profile['xp'])}",
                    "guild_rank": guild_rank,
                    "guild_name": profile["guild_name"],
                    "money": f"{profile['money']}",
                    "pvp_wins": f"{profile['pvpwins']}",
                    "marriage": marriage,
                    "god": profile["god"] or _("No God"),
                    "adventure_name": adventure_name,
                    "adventure_time": adventure_time,
                    "badges": badges,
                },
                headers={"Authorization": self.bot.config.external.okapi_token},
        ) as req:
            if req.status == 200:

                img = await req.text()



            else:
                # Error, means try reading the response JSON error
                try:
                    error_json = await req.json()
                    return await ctx.send(
                        _(
                            "There was an error processing your image. Reason: {reason} ({detail})"
                        ).format(
                            reason=error_json["reason"], detail=error_json["detail"]
                        )
                    )
                except ContentTypeError:
                    return await ctx.send(
                        _("Unexpected internal error when generating image.")
                    )
                except Exception:
                    return await ctx.send(_("Unexpected error when generating image."))

            async with self.bot.trusted_session.get(img) as resp:
                bytebuffer = await resp.read()
                if resp.status != 200:
                    return await ctx.send("Error failed to fetch image")

        await ctx.send(
            _("Your Profile:"),
            file=discord.File(fp=io.BytesIO(bytebuffer), filename="image.png"),
        )

    @commands.command(
        aliases=["p2", "pp"], brief=_("View someone's profile differently")
    )
    @locale_doc
    async def profile2(self, ctx, *, target: discord.User = None):
        _(
            """`[target]` - The person whose profile to view

            View someone's profile. This will send an embed rather than an image and is usually faster."""
        )
        target = target or ctx.author
        rank_money, rank_xp = await self.bot.get_ranks_for(target)

        items = await self.bot.get_equipped_items_for(target)
        async with self.bot.pool.acquire() as conn:
            p_data = await conn.fetchrow(
                'SELECT * FROM profile WHERE "user"=$1;', target.id
            )
            if not p_data:
                return await ctx.send(
                    _("**{target}** does not have a character.").format(target=target)
                )
            mission = await self.bot.get_adventure(target)
            guild = await conn.fetchval(
                'SELECT name FROM guild WHERE "id"=$1;', p_data["guild"]
            )
        try:
            colour = p_data["colour"]
            colour = discord.Colour.from_rgb(
                colour["red"], colour["green"], colour["blue"]
            )
        except ValueError:
            colour = 0x000000
        if mission:
            timeleft = str(mission[1]).split(".")[0] if not mission[2] else "Finished"

        right_hand = None
        left_hand = None

        any_count = sum(1 for i in items if i["hand"] == "any")
        if len(items) == 2 and any_count == 1 and items[0]["hand"] == "any":
            items = [items[1], items[0]]

        for i in items:
            if i["hand"] == "both":
                right_hand, left_hand = i, i
            elif i["hand"] == "left":
                left_hand = i
            elif i["hand"] == "right":
                right_hand = i
            elif i["hand"] == "any":
                if right_hand is None:
                    right_hand = i
                else:
                    left_hand = i

        right_hand = (
            f"{right_hand['name']} - {right_hand['damage'] + right_hand['armor']}"
            if right_hand
            else _("None Equipped")
        )
        left_hand = (
            f"{left_hand['name']} - {left_hand['damage'] + left_hand['armor']}"
            if left_hand
            else _("None Equipped")
        )
        level = rpgtools.xptolevel(p_data["xp"])
        em = discord.Embed(colour=colour, title=f"{target}: {p_data['name']}")
        em.set_thumbnail(url=target.display_avatar.url)
        em.add_field(
            name=_("General"),
            value=_(
                """\
**Money**: `${money}`
**Level**: `{level}`
**Class**: `{class_}`
**Race**: `{race}`
**PvP Wins**: `{pvp}`
**Guild**: `{guild}`"""
            ).format(
                money=p_data["money"],
                level=level,
                class_="/".join(p_data["class"]),
                race=p_data["race"],
                pvp=p_data["pvpwins"],
                guild=guild,
            ),
        )
        em.add_field(
            name=_("Ranks"),
            value=_("**Richest**: `{rank_money}`\n**XP**: `{rank_xp}`").format(
                rank_money=rank_money, rank_xp=rank_xp
            ),
        )
        em.add_field(
            name=_("Equipment"),
            value=_("Right Hand: {right_hand}\nLeft Hand: {left_hand}").format(
                right_hand=right_hand, left_hand=left_hand
            ),
        )
        if mission:
            em.add_field(name=_("Mission"), value=f"{mission[0]} - {timeleft}")
        await ctx.send(embed=em)

    @checks.has_char()
    @commands.command(brief=_("Show your current luck"))
    @locale_doc
    async def luck(self, ctx):
        _(
            """Shows your current luck value.

            Luck updates once a week for everyone, usually on Monday. It depends on your God.
            Luck influences your adventure survival chances as well as the rewards.

            Luck is decided randomly within the Gods' luck boundaries. You can find your God's boundaries [here](https://wiki.idlerpg.xyz/index.php?title=Gods#List_of_Deities).

            If you have enough favor to place in the top 25 followers, you will gain additional luck:
              - The top 25 to 21 will gain +0.1 luck
              - The top 20 to 16 will gain +0.2 luck
              - The top 15 to 11 will gain +0.3 luck
              - The top 10 to 6 will gain +0.4 luck
              - The top 5 to 1 will gain +0.5 luck

            If you follow a new God (or become Godless), your luck will not update instantly, it will update with everyone else's luck on Monday."""
        )
        await ctx.send(
            _(
                "Your current luck multiplier is `{luck}x` (≈{percent}% {adj} than"
                " usual (usual=1))."
            ).format(
                luck=ctx.character_data["luck"],
                percent=abs((ctx.character_data["luck"] - 1) * 100),
                adj=_("more") if ctx.character_data["luck"] > 1 else _("less"),
            )
        )

    @checks.has_char()
    @commands.command(
        aliases=["money", "e", "balance", "bal"], brief=_("Shows your balance")
    )
    @locale_doc
    async def economy(self, ctx):
        _(
            """Shows the amount of money you currently have.

            Among other ways, you can get more money by:
              - Playing adventures
              - Selling unused equipment
              - Gambling"""
        )
        await ctx.send(
            _("You currently have **${money}**, {author}!").format(
                money=ctx.character_data["money"], author=ctx.author.mention
            )
        )

    @checks.has_char()
    @commands.command(brief=_("Show a player's current XP"))
    @locale_doc
    async def xp(self, ctx, user: UserWithCharacter = None):
        _(
            """`[user]` - The player whose XP and level to show; defaults to oneself

            Show a player's XP and level.

            You can gain more XP by:
              - Completing adventures
              - Exchanging loot items for XP"""
        )
        user = user or ctx.author
        if user.id == ctx.author.id:
            points = ctx.character_data["xp"]
            await ctx.send(
                _(
                    "You currently have **{points} XP**, which means you are on Level"
                    " **{level}**. Missing to next level: **{missing}**"
                ).format(
                    points=points,
                    level=rpgtools.xptolevel(points),
                    missing=rpgtools.xptonextlevel(points),
                )
            )
        else:
            points = ctx.user_data["xp"]
            await ctx.send(
                _(
                    "{user} has **{points} XP** and is on Level **{level}**. Missing to"
                    " next level: **{missing}**"
                ).format(
                    user=user,
                    points=points,
                    level=rpgtools.xptolevel(points),
                    missing=rpgtools.xptonextlevel(points),
                )
            )

    def invembed(self, ctx, ret, currentpage, maxpage):
        result = discord.Embed(
            title=_("{user}'s inventory includes").format(user=ctx.disp),
            colour=discord.Colour.blurple(),
        )
        for weapon in ret:
            if weapon["equipped"]:
                eq = _("(**Equipped**)")
            else:
                eq = ""
            statstr = (
                _("Damage: `{damage}`").format(damage=weapon["damage"])
                if weapon["type"] != "Shield"
                else _("Armor: `{armor}`").format(armor=weapon["armor"])
            )
            signature = (
                _("\nSignature: *{signature}*").format(signature=y)
                if (y := weapon["signature"])
                else ""
            )
            result.add_field(
                name=f"{weapon['name']} {eq}",
                value=_(
                    "ID: `{id}`, Type: `{type_}` (uses {hand} hand(s)) with {statstr}."
                    " Value is **${value}**{signature}"
                ).format(
                    id=weapon["id"],
                    type_=weapon["type"],
                    hand=weapon["hand"],
                    statstr=statstr,
                    value=weapon["value"],
                    signature=signature,
                ),
                inline=False,
            )
        result.set_footer(
            text=_("Page {page} of {maxpages}").format(
                page=currentpage + 1, maxpages=maxpage + 1
            )
        )
        return result

    @checks.has_char()
    @commands.command(aliases=["inv", "i"], brief=_("Show your gear items"))
    @locale_doc
    async def inventory(
            self,
            ctx,
            itemtype: str | None = "All",
            lowest: IntFromTo(0, 101) = 0,
            highest: IntFromTo(0, 101) = 101,
    ):
        _(
            """`[itemtype]` - The type of item to show; defaults to all items
            `[lowest]` - The lower boundary of items to show; defaults to 0
            `[highest]` - The upper boundary of items to show; defaults to 101

            Show your gear items. Items that are in the market will not be shown.

            Gear items can be equipped, sold and given away, or upgraded and merged to make them stronger.
            You can gain gear items by completing adventures, opening crates, or having your pet hunt for them, if you are a ranger.

            To sell unused items for their value, use `{prefix}merch`. To put them up on the global player market, use `{prefix}sell`."""
        )
        itemtype = itemtype.title()

        if highest < lowest:
            return await ctx.send(
                _("Make sure that the `highest` value is greater than `lowest`.")
            )
        itemtype_cls = ItemType.from_string(itemtype)
        if itemtype != "All" and itemtype_cls is None:
            return await ctx.send(
                _(
                    "Please select a valid item type or `all`. Available types:"
                    " `{all_types}`"
                ).format(all_types=", ".join([t.name for t in ALL_ITEM_TYPES]))
            )
        if itemtype == "All":
            ret = await self.bot.pool.fetch(
                "SELECT ai.*, i.equipped FROM profile p JOIN allitems ai ON"
                " (p.user=ai.owner) JOIN inventory i ON (ai.id=i.item) WHERE"
                ' p."user"=$1 AND ((ai."damage"+ai."armor" BETWEEN $2 AND $3) OR'
                ' i."equipped") ORDER BY i."equipped" DESC, ai."damage"+ai."armor"'
                " DESC;",
                ctx.author.id,
                lowest,
                highest,
            )
        else:
            ret = await self.bot.pool.fetch(
                "SELECT ai.*, i.equipped FROM profile p JOIN allitems ai ON"
                " (p.user=ai.owner) JOIN inventory i ON (ai.id=i.item) WHERE"
                ' p."user"=$1 AND ((ai."damage"+ai."armor" BETWEEN $2 AND $3 AND'
                ' ai."type"=$4)  OR i."equipped") ORDER BY i."equipped" DESC,'
                ' ai."damage"+ai."armor" DESC;',
                ctx.author.id,
                lowest,
                highest,
                itemtype,
            )
        if not ret:
            return await ctx.send(_("Your inventory is empty."))
        allitems = list(chunks(ret, 5))
        maxpage = len(allitems) - 1
        embeds = [
            self.invembed(ctx, chunk, idx, maxpage)
            for idx, chunk in enumerate(allitems)
        ]
        await self.bot.paginator.Paginator(extras=embeds).paginate(ctx)

    def lootembed(self, ctx, ret, currentpage, maxpage):
        result = discord.Embed(
            title=_("{user} has the following loot items.").format(user=ctx.disp),
            colour=discord.Colour.blurple(),
        )
        for item in ret:
            result.add_field(
                name=item["name"],
                value=_("ID: `{id}` Value is **{value}**").format(
                    id=item["id"], value=item["value"]
                ),
                inline=False,
            )
        result.set_footer(
            text=_("Page {page} of {maxpages}").format(
                page=currentpage + 1, maxpages=maxpage + 1
            )
        )
        return result

    @checks.has_char()
    @commands.command(aliases=["loot"], brief=_("Show your loot items"))
    @locale_doc
    async def items(self, ctx):
        _(
            """Show your loot items.

            Loot items can be exchanged for money or XP, or sacrificed to your God to gain favor points.

            You can gain loot items by completing adventures. The higher the difficulty, the higher the chance to get loot.
            If you are a Ritualist, your loot chances are doubled. Check [our wiki](https://wiki.idlerpg.xyz/index.php?title=Loot#Probability) for the exact chances."""
        )
        ret = await self.bot.pool.fetch(
            'SELECT * FROM loot WHERE "user"=$1 ORDER BY "value" DESC, "id" DESC;',
            ctx.author.id,
        )
        if not ret:
            return await ctx.send(_("You do not have any loot at this moment."))
        allitems = list(chunks(ret, 7))
        maxpage = len(allitems) - 1
        embeds = [
            self.lootembed(ctx, chunk, idx, maxpage)
            for idx, chunk in enumerate(allitems)
        ]
        await self.bot.paginator.Paginator(extras=embeds).paginate(ctx)

    @checks.has_char()
    @user_cooldown(180, identifier="sacrificeexchange")
    @commands.command(aliases=["ex"], brief=_("Exchange your loot for money or XP"))
    @locale_doc
    async def exchange(self, ctx, *loot_ids: int):
        _(
            """`[loot_ids...]` - The loot IDs to exchange; defaults to all loot

            Exchange your loot for money or XP, the bot will let you choose.

            If you choose money, you will get the loots' combined value in cash. For XP, you will get 1/4th of the combined value in XP."""
        )
        if none_given := (len(loot_ids) == 0):
            value, count = await self.bot.pool.fetchval(
                'SELECT (SUM("value"), COUNT(*)) FROM loot WHERE "user"=$1',
                ctx.author.id,
            )
            if count == 0:
                await self.bot.reset_cooldown(ctx)
                return await ctx.send(_("You don't have any loot."))
        else:
            value, count = await self.bot.pool.fetchval(
                'SELECT (SUM("value"), COUNT("value")) FROM loot WHERE "id"=ANY($1)'
                ' AND "user"=$2;',
                loot_ids,
                ctx.author.id,
            )
            if not count:
                await self.bot.reset_cooldown(ctx)
                return await ctx.send(
                    _("You don't own any loot items with the IDs: {itemids}").format(
                        itemids=", ".join([str(loot_id) for loot_id in loot_ids])
                    )
                )

        value = int(value)
        reward = await self.bot.paginator.Choose(
            title=_(f"Select a reward for the {count} items"),
            placeholder=_("Select a reward"),
            footer=_("Do you want favor? {prefix}sacrifice instead").format(
                prefix=ctx.clean_prefix
            ),
            return_index=True,
            entries=[f"**${value}**", _("**{value} XP**").format(value=value // 4)],
            choices=[f"${value}", _("{value} XP").format(value=value // 4)],
        ).paginate(ctx)
        reward = ["money", "xp"][reward]
        if reward == "xp":
            old_level = rpgtools.xptolevel(ctx.character_data["xp"])
            value = value // 4

        async with self.bot.pool.acquire() as conn:
            if none_given:
                await conn.execute('DELETE FROM loot WHERE "user"=$1;', ctx.author.id)
            else:
                await conn.execute(
                    'DELETE FROM loot WHERE "id"=ANY($1) AND "user"=$2;',
                    loot_ids,
                    ctx.author.id,
                )
            await conn.execute(
                f'UPDATE profile SET "{reward}"="{reward}"+$1 WHERE "user"=$2;',
                value,
                ctx.author.id,
            )
            await self.bot.log_transaction(
                ctx,
                from_=1,
                to=ctx.author.id,
                subject="exchange",
                data={"Reward": reward, "Amount": value},
                conn=conn,
            )
        if none_given:
            text = _(
                "You received **{reward}** when exchanging all of your loot."
            ).format(reward=f"${value}" if reward == "money" else f"{value} XP")
        else:
            text = _(
                "You received **{reward}** when exchanging loot item(s) `{loot_ids}`. "
            ).format(
                reward=f"${value}" if reward == "money" else f"{value} XP",
                loot_ids=", ".join([str(lootid) for lootid in loot_ids]),
            )
        additional = _("Skipped `{amount}` because they did not belong to you.").format(
            amount=len(loot_ids) - count
        )
        # if len(loot_ids) > count else ""

        await ctx.send(text + (additional if len(loot_ids) > count else ""))

        if reward == "xp":
            new_level = int(rpgtools.xptolevel(ctx.character_data["xp"] + value))
            if old_level != new_level:
                await self.bot.process_levelup(ctx, new_level, old_level)

        await self.bot.reset_cooldown(ctx)

    @user_cooldown(180)
    @checks.has_char()
    @commands.command(aliases=["use"], brief=_("Equip an item"))
    @locale_doc
    async def equip(self, ctx, itemid: int):
        _(
            """`<itemid>` - The ID of the item to equip

            Equip an item by its ID, you can find the item IDs in your inventory.

            Each item has an assigned hand slot,
              "any" meaning that the item can go in either hand,
              "both" meaning it takes both hands,
              "left" and "right" should be clear.

            You cannot equip two items that use the same hand, or a second item if the one your have equipped is two-handed."""
        )
        async with self.bot.pool.acquire() as conn:
            item = await conn.fetchrow(
                'SELECT ai.* FROM inventory i JOIN allitems ai ON (i."item"=ai."id")'
                ' WHERE ai."owner"=$1 and ai."id"=$2;',
                ctx.author.id,
                itemid,
            )
            if not item:
                return await ctx.send(
                    _("You don't own an item with the ID `{itemid}`.").format(
                        itemid=itemid
                    )
                )
            olditems = await conn.fetch(
                "SELECT ai.* FROM profile p JOIN allitems ai ON (p.user=ai.owner) JOIN"
                " inventory i ON (ai.id=i.item) WHERE i.equipped IS TRUE AND"
                " p.user=$1;",
                ctx.author.id,
            )
            put_off = []
            if olditems:
                num_any = sum(1 for i in olditems if i["hand"] == "any")
                if len(olditems) == 1 and olditems[0]["hand"] == "both":
                    await conn.execute(
                        'UPDATE inventory SET "equipped"=False WHERE "item"=$1;',
                        olditems[0]["id"],
                    )
                    put_off = [olditems[0]["id"]]
                elif item["hand"] == "both":
                    all_ids = [i["id"] for i in olditems]
                    await conn.execute(
                        'UPDATE inventory SET "equipped"=False WHERE "item"=ANY($1);',
                        all_ids,
                    )
                    put_off = all_ids
                else:
                    if len(olditems) < 2:
                        if (
                                item["hand"] != "any"
                                and olditems[0]["hand"] == item["hand"]
                        ):
                            await conn.execute(
                                'UPDATE inventory SET "equipped"=False WHERE'
                                ' "item"=$1;',
                                olditems[0]["id"],
                            )
                            put_off = [olditems[0]["id"]]
                    elif (
                            item["hand"] == "left" or item["hand"] == "right"
                    ) and num_any < 2:
                        item_to_remove = [
                            i for i in olditems if i["hand"] == item["hand"]
                        ]
                        if not item_to_remove:
                            item_to_remove = [i for i in olditems if i["hand"] == "any"]
                        item_to_remove = item_to_remove[0]["id"]
                        await conn.execute(
                            'UPDATE inventory SET "equipped"=False WHERE "item"=$1;',
                            item_to_remove,
                        )
                        put_off = [item_to_remove]
                    else:
                        item_to_remove = await self.bot.paginator.Choose(
                            title=_("Select an item to unequip"),
                            return_index=True,
                            entries=[
                                f"{i['name']}, {i['type']}, {i['damage'] + i['armor']}"
                                for i in olditems
                            ],
                            choices=[i["name"] for i in olditems],
                        ).paginate(ctx)
                        item_to_remove = olditems[item_to_remove]["id"]
                        await conn.execute(
                            'UPDATE inventory SET "equipped"=False WHERE "item"=$1;',
                            item_to_remove,
                        )
                        put_off = [item_to_remove]
            await conn.execute(
                'UPDATE inventory SET "equipped"=True WHERE "item"=$1;', itemid
            )
        await self.bot.reset_cooldown(ctx)
        if put_off:
            await ctx.send(
                _(
                    "Successfully equipped item `{itemid}` and put off item(s)"
                    " {olditems}."
                ).format(
                    olditems=", ".join(f"`{i}`" for i in put_off), itemid=item["id"]
                )
            )
        else:
            await ctx.send(
                _("Successfully equipped item `{itemid}`.").format(itemid=itemid)
            )

    @checks.has_char()
    @commands.command(brief=_("Unequip an item"))
    @locale_doc
    async def unequip(self, ctx, itemid: int):
        _(
            """`<itemid>` - The ID of the item to unequip

            Unequip one of your equipped items. This has no benefit whatsoever."""
        )
        async with self.bot.pool.acquire() as conn:
            item = await conn.fetchrow(
                'SELECT * FROM inventory i JOIN allitems ai ON (i."item"=ai."id") WHERE'
                ' ai."owner"=$1 and ai."id"=$2;',
                ctx.author.id,
                itemid,
            )
            if not item:
                return await ctx.send(
                    _("You don't own an item with the ID `{itemid}`.").format(
                        itemid=itemid
                    )
                )
            if not item["equipped"]:
                return await ctx.send(_("You don't have this item equipped."))
            await conn.execute(
                'UPDATE inventory SET "equipped"=False WHERE "item"=$1;', itemid
            )
        await ctx.send(
            _("Successfully unequipped item `{itemid}`.").format(itemid=itemid)
        )

    @checks.has_char()
    @user_cooldown(3600)
    @commands.command(brief=_("Merge two items to make a stronger one"))
    @locale_doc
    async def merge(self, ctx, firstitemid: int, seconditemid: int):
        _(
            """`<firstitemid>` - The ID of the first item
            `<seconditemid>` - The ID of the second item

            Merges two items to a better one.

            ⚠ The first item will be upgraded by +1, the second item will be destroyed.

            The two items must be of the same item type and within a 5 stat range of each other.
            For example, if the first item is a 23 damage Scythe, the second item must be a Scythe with damage 18 to 28.

            One handed weapons can be merged up to 41, two handed items up to 82

            (This command has a cooldown of 1 hour.)"""
        )
        if firstitemid == seconditemid:
            await self.bot.reset_cooldown(ctx)
            return await ctx.send(_("Good luck with that."))
        async with self.bot.pool.acquire() as conn:
            item = await conn.fetchrow(
                'SELECT * FROM allitems WHERE "id"=$1 AND "owner"=$2;',
                firstitemid,
                ctx.author.id,
            )
            item2 = await conn.fetchrow(
                'SELECT * FROM allitems WHERE "id"=$1 AND "owner"=$2;',
                seconditemid,
                ctx.author.id,
            )
            if not item or not item2:
                await self.bot.reset_cooldown(ctx)
                return await ctx.send(_("You don't own both of these items."))
            if item["type"] != item2["type"]:
                await self.bot.reset_cooldown(ctx)
                return await ctx.send(
                    _(
                        "The items are of unequal type. You may only merge a sword with"
                        " a sword or a shield with a shield."
                    )
                )
            stat = "damage" if item["type"] != "Shield" else "armor"
            min_ = item[stat] - 5
            main = item[stat]
            main2 = item2[stat]
            max_ = item[stat] + 5
            main_hand = item["hand"]
            if (main > 40 and main_hand != "both") or (
                    main > 81 and main_hand == "both"
            ):
                await self.bot.reset_cooldown(ctx)
                return await ctx.send(
                    _("This item is already on the maximum upgrade level.")
                )
            if not min_ <= main2 <= max_:
                await self.bot.reset_cooldown(ctx)
                return await ctx.send(
                    _(
                        "The second item's stat must be in the range of `{min_}` to"
                        " `{max_}` to upgrade an item with the stat of `{stat}`."
                    ).format(min_=min_, max_=max_, stat=main)
                )
            await conn.execute(
                f'UPDATE allitems SET "{stat}"="{stat}"+1 WHERE "id"=$1;', firstitemid
            )
            await conn.execute('DELETE FROM inventory WHERE "item"=$1;', seconditemid)
            await conn.execute('DELETE FROM allitems WHERE "id"=$1;', seconditemid)
        await ctx.send(
            _(
                "The {stat} of your **{item}** is now **{newstat}**. The other item was"
                " destroyed."
            ).format(stat=stat, item=item["name"], newstat=main + 1)
        )

    @checks.has_char()
    @user_cooldown(3600)
    @commands.command(aliases=["upgrade"], brief=_("Upgrade an item"))
    @locale_doc
    async def upgradeweapon(self, ctx, itemid: int):
        _(
            """`<itemid>` - The ID of the item to upgrade

            Upgrades an item's stat by 1.
            The price to upgrade an item is 250 times its current stat. For example, upgrading a 15 damage sword will cost $3,750.

            One handed weapons can be upgraded up to 41, two handed items up to 82.

            (This command has a cooldown of 1 hour.)"""
        )
        async with self.bot.pool.acquire() as conn:
            item = await conn.fetchrow(
                'SELECT * FROM allitems WHERE "id"=$1 AND "owner"=$2;',
                itemid,
                ctx.author.id,
            )
            if not item:
                await self.bot.reset_cooldown(ctx)
                return await ctx.send(
                    _("You don't own an item with the ID `{itemid}`.").format(
                        itemid=itemid
                    )
                )
            if item["type"] != "Shield":
                stattoupgrade = "damage"
                pricetopay = int(item["damage"] * 250)
            elif item["type"] == "Shield":
                stattoupgrade = "armor"
                pricetopay = int(item["armor"] * 250)
            stat = int(item[stattoupgrade])
            hand = item["hand"]
            if (stat > 40 and hand != "both") or (stat > 81 and hand == "both"):
                await self.bot.reset_cooldown(ctx)
                return await ctx.send(
                    _("Your weapon already reached the maximum upgrade level.")
                )

        if not await ctx.confirm(
                _(
                    "Are you sure you want to upgrade this item: {item}? It will cost"
                    " **${pricetopay}**."
                ).format(item=item["name"], pricetopay=pricetopay)
        ):
            return await ctx.send(_("Weapon upgrade cancelled."))
        if not await checks.has_money(self.bot, ctx.author.id, pricetopay):
            await self.bot.reset_cooldown(ctx)
            return await ctx.send(
                _(
                    "You are too poor to upgrade this item. The upgrade costs"
                    " **${pricetopay}**, but you only have **${money}**."
                ).format(pricetopay=pricetopay, money=ctx.character_data["money"])
            )
        async with self.bot.pool.acquire() as conn:
            await conn.execute(
                f'UPDATE allitems SET {stattoupgrade}={stattoupgrade}+1 WHERE "id"=$1;',
                itemid,
            )
            await conn.execute(
                'UPDATE profile SET "money"="money"-$1 WHERE "user"=$2;',
                pricetopay,
                ctx.author.id,
            )
            await self.bot.log_transaction(
                ctx,
                from_=ctx.author.id,
                to=2,
                subject="money",
                data={"Amount": pricetopay},
                conn=conn,
            )
        await ctx.send(
            _(
                "The {stat} of your **{item}** is now **{newstat}**. **${pricetopay}**"
                " has been taken off your balance."
            ).format(
                stat=stattoupgrade,
                item=item["name"],
                newstat=int(item[stattoupgrade]) + 1,
                pricetopay=pricetopay,
            )
        )

    @checks.has_char()
    @commands.command(brief=_("Give someone money"))
    @locale_doc
    async def give(
            self, ctx, money: IntFromTo(1, 100_000_000), other: MemberWithCharacter
    ):
        _(
            """`<money>` - The amount of money to give to the other person, cannot exceed 100,000,000
            `[other]` - The person to give the money to

            Gift money! It will be removed from you and added to the other person."""
        )
        if other == ctx.author:
            return await ctx.send(_("No cheating!"))
        elif other == ctx.me:
            return await ctx.send(
                _("For me? I'm flattered, but I can't accept this...")
            )
        if ctx.character_data["money"] < money:
            return await ctx.send(_("You are too poor."))
        async with self.bot.pool.acquire() as conn:
            authormoney = await conn.fetchval(
                'UPDATE profile SET "money"="money"-$1 WHERE "user"=$2 RETURNING'
                ' "money";',
                money,
                ctx.author.id,
            )
            othermoney = await conn.fetchval(
                'UPDATE profile SET "money"="money"+$1 WHERE "user"=$2 RETURNING'
                ' "money";',
                money,
                other.id,
            )
            await self.bot.log_transaction(
                ctx,
                from_=ctx.author,
                to=other,
                subject="money",
                data={"Amount": money},
                conn=conn,
            )
        await ctx.send(
            _(
                "Success!\n{other} now has **${othermoney}**, you now have"
                " **${authormoney}**."
            ).format(
                other=other.mention, othermoney=othermoney, authormoney=authormoney
            )
        )

    @checks.has_char()
    @commands.command(brief=_("Rename your character"))
    @locale_doc
    async def rename(self, ctx, *, name: str = None):
        _(
            """`[name]` - The name to use; if not given, this will be interactive

            Renames your character. The name must be from 3 to 20 characters long."""
        )
        if not name:
            await ctx.send(
                _(
                    "What shall your character's name be? (Minimum 3 Characters,"
                    " Maximum 20)"
                )
            )

            def mycheck(amsg):
                return amsg.author == ctx.author

            try:
                name = await self.bot.wait_for("message", timeout=60, check=mycheck)
            except asyncio.TimeoutError:
                return await ctx.send(_("Timeout expired. Retry!"))
            name = name.content
        if len(name) > 2 and len(name) < 21:
            if "`" in name:
                return await ctx.send(
                    _(
                        "Illegal character (`) found in the name. Please try again and"
                        " choose another name."
                    )
                )
            await self.bot.pool.execute(
                'UPDATE profile SET "name"=$1 WHERE "user"=$2;', name, ctx.author.id
            )
            await ctx.send(_("Character name updated."))
        elif len(name) < 3:
            await ctx.send(_("Character names must be at least 3 characters!"))
        elif len(name) > 20:
            await ctx.send(_("Character names mustn't exceed 20 characters!"))

    @checks.has_char()
    @commands.command(aliases=["rm", "del"], brief=_("Delete your character"))
    @locale_doc
    async def delete(self, ctx):
        _(
            """Deletes your character. There is no way to get your character data back after deletion.

            Deleting your character also removes:
              - Your guild if you own one
              - Your alliance's city ownership
              - Your marriage and children"""
        )
        if not await ctx.confirm(
                _(
                    "Are you absolutely sure you want to delete your character? React in"
                    " the next 30 seconds to confirm.\n**This cannot be undone.**"
                )
        ):
            return await ctx.send(_("Cancelled deletion of your character."))
        async with self.bot.pool.acquire() as conn:
            g = await conn.fetchval(
                'DELETE FROM guild WHERE "leader"=$1 RETURNING "id";', ctx.author.id
            )
            if g:
                await conn.execute(
                    'UPDATE profile SET "guildrank"=$1, "guild"=$2 WHERE "guild"=$3;',
                    "Member",
                    0,
                    g,
                )
                await conn.execute('UPDATE city SET "owner"=1 WHERE "owner"=$1;', g)
            if partner := ctx.character_data["marriage"]:
                await conn.execute(
                    'UPDATE profile SET "marriage"=$1 WHERE "user"=$2;',
                    0,
                    partner,
                )
            await conn.execute(
                'UPDATE children SET "mother"=$1, "father"=0 WHERE ("father"=$1 AND'
                ' "mother"=$2) OR ("father"=$2 AND "mother"=$1);',
                partner,
                ctx.author.id,
            )
            await self.bot.delete_profile(ctx.author.id, conn=conn)
        await self.bot.delete_adventure(ctx.author)
        await ctx.send(
            _("Successfully deleted your character. Sorry to see you go :frowning:")
        )

    @checks.has_char()
    @commands.command(aliases=["color"], brief=_("Update your profile color"))
    @locale_doc
    async def colour(self, ctx, *, colour: str):
        _(
            """`<color>` - The color to use, see below for allowed format

            Sets your profile text colour. The format may be #RGB, #RRGGBB, CSS3 defaults like "cyan", a rgb(r, g, b) tuple or a rgba(r, g, b, a) tuple

            A tuple is a data type consisting of multiple parts. To make a tuple for this command, seperate your values with a comma, and surround them with parantheses.
            Here is an example of a tuple with four values: `(128,256,0,0.5)`

            This will change the text color in `{prefix}profile` and the embed color in `{prefix}profile2`."""
        )
        try:
            rgba = colors.parse(colour)
        except ValueError:
            return await ctx.send(
                _(
                    "Format for colour is `#RGB`, `#RRGGBB`, a colour code like `cyan`"
                    " or rgb/rgba values like (255, 255, 255, 0.5)."
                )
            )
        await self.bot.pool.execute(
            'UPDATE profile SET "colour"=$1 WHERE "user"=$2;',
            (rgba.red, rgba.green, rgba.blue, rgba.alpha),
            ctx.author.id,
        )
        await ctx.send(
            _("Successfully set your profile colour to `{colour}`.").format(
                colour=colour
            )
        )

    @checks.has_char()
    @commands.command(brief=_("Claim your profile badges"))
    @locale_doc
    async def claimbadges(self, ctx: Context) -> None:
        _(
            """Claim all badges for your profile based on your roles. This command can only be used in the support server."""
        )
        if not ctx.guild or ctx.guild.id != self.bot.config.game.support_server_id:
            await ctx.send(_("This command can only be used in the support server."))
            return

        roles = {
            "Contributor": Badge.CONTRIBUTOR,
            "Designer": Badge.DESIGNER,
            "Developer": Badge.DEVELOPER,
            "Game Designer": Badge.GAME_DESIGNER,
            "Game Masters": Badge.GAME_MASTER,
            "Support Team": Badge.SUPPORT,
            "Betasquad": Badge.TESTER,
            "Veterans": Badge.VETERAN,
        }

        badges = None

        for role in ctx.author.roles:
            if (badge := roles.get(role.name)) is not None:
                if badges is None:
                    badges = badge
                else:
                    badges |= badge

        if badges is not None:
            await self.bot.pool.execute(
                'UPDATE profile SET "badges"=$1 WHERE "user"=$2;',
                badges.to_db(),
                ctx.author.id,
            )

        await ctx.send(_("Successfully updated your badges."))


async def setup(bot):
    await bot.add_cog(Profile(bot))
