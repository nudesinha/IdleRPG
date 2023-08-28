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

from asyncpg.exceptions import UniqueViolationError
from discord.ext import commands
from discord.http import handle_message_parameters
import json

from classes.converters import CrateRarity, IntFromTo, IntGreaterThan, UserWithCharacter
from classes.items import ItemType
from cogs.shard_communication import user_on_cooldown as user_cooldown
from utils import random
from utils.checks import has_char, is_gm
from utils.i18n import _, locale_doc

import copy
import io
import re
import textwrap
import traceback

from contextlib import redirect_stdout

import discord

from discord.ext import commands

from utils.checks import has_char, is_gm
from classes.badges import Badge, BadgeConverter
from classes.bot import Bot
from classes.context import Context
from classes.converters import UserWithCharacter
from utils import shell
from utils.misc import random_token


class GameMaster(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.top_auction = None
        self.auction_entry = None
        self.patron_ids = self.load_patron_ids()

    @is_gm()
    @commands.command(brief=_("Publish an announcement"))
    @locale_doc
    async def publish(self, ctx, message: discord.Message):
        _("Publish a message from an announement channel")
        try:
            await message.publish()
            await ctx.send(_("Message has been published!"))
        except discord.Forbidden:
            await ctx.send(_("This message is not from an announcement channel!"))

    @is_gm()
    @commands.command(
        aliases=["cleanshop", "cshop"], hidden=True, brief=_("Clean up the shop")
    )
    @locale_doc
    async def clearshop(self, ctx):
        _(
            """Remove items from the shop that have been there for more than 14 days, returning them to the owners' inventories.

            Only Game Masters can use this command."""
        )
        async with self.bot.pool.acquire() as conn:
            timed_out = await conn.fetch(
                """DELETE FROM market WHERE "published" + '14 days'::interval < NOW() RETURNING *;""",
                timeout=600,
            )
            await conn.executemany(
                'INSERT INTO inventory ("item", "equipped") VALUES ($1, $2);',
                [(i["item"], False) for i in timed_out],
                timeout=600,
            )
        await ctx.send(
            _("Cleared {num} shop items which timed out.").format(num=len(timed_out))
        )

    @is_gm()
    @commands.command(
        hidden=True, aliases=["gmcdc"], brief=_("Clear donator cache for a user")
    )
    @locale_doc
    async def gmcleardonatorcache(self, ctx, *, other: discord.Member):
        _(
            """`<other>` - A server member

            Clears the cached donator rank for a user globally, allowing them to use the new commands after donating.

            Only Game Masters can use this command."""
        )
        await self.bot.clear_donator_cache(other)
        await ctx.send(_("Done"))

    @is_gm()
    @commands.command(hidden=True, brief=_("Bot-ban a user"))
    @locale_doc
    async def gmban(self, ctx, other: int | discord.User, *, reason: str = ""):
        _(
            """`<other>` - A discord User

            Bans a user from the bot, prohibiting them from using commands and reactions.

            Only Game Masters can use this command."""
        )
        id_ = other if isinstance(other, int) else other.id

        try:
            await self.bot.pool.execute(
                'INSERT INTO bans ("user", "reason") VALUES ($1, $2);', id_, reason
            )
            self.bot.bans.add(id_)
            await self.bot.reload_bans()

            await ctx.send(_("Banned: {other}").format(other=other))

            with handle_message_parameters(
                    content="**{gm}** banned **{other}**.\n\nReason: *{reason}*".format(
                        gm=ctx.author,
                        other=other,
                        reason=reason or f"<{ctx.message.jump_url}>",
                    )
            ) as params:
                await self.bot.http.send_message(
                    self.bot.config.game.gm_log_channel,
                    params=params,
                )
        except UniqueViolationError:
            await ctx.send(_("{other} is already banned.").format(other=other))

    @is_gm()
    @commands.command(hidden=True, brief=_("Bot-unban a user"))
    @locale_doc
    async def gmunban(self, ctx, other: int | discord.User, *, reason: str = ""):
        _(
            """`<other>` - A discord User

            Unbans a user from the bot, allowing them to use commands and reactions again.

            Only Game Masters can use this command."""
        )
        id_ = other if isinstance(other, int) else other.id
        await self.bot.pool.execute('DELETE FROM bans WHERE "user"=$1;', id_)

        try:
            self.bot.bans.remove(id_)
            await self.bot.reload_bans()

            await ctx.send(_("Unbanned: {other}").format(other=other))

            with handle_message_parameters(
                    content="**{gm}** unbanned **{other}**.\n\nReason: *{reason}*".format(
                        gm=ctx.author,
                        other=other,
                        reason=reason or f"<{ctx.message.jump_url}>",
                    )
            ) as params:
                await self.bot.http.send_message(
                    self.bot.config.game.gm_log_channel,
                    params=params,
                )
        except KeyError:
            await ctx.send(_("{other} is not banned.").format(other=other))

    @is_gm()
    @commands.command(hidden=True, brief=_("Create money"))
    @locale_doc
    async def gmgive(
            self,
            ctx,
            money: int,
            other: UserWithCharacter,
            *,
            reason: str = None,
    ):
        _(
            """`<money>` - the amount of money to generate for the user
            `<other>` - A discord User with a character
            `[reason]` - The reason this action was done, defaults to the command message link

            Gives a user money without subtracting it from the command author's balance.

            Only Game Masters can use this command."""
        )
        await self.bot.pool.execute(
            'UPDATE profile SET "money"="money"+$1 WHERE "user"=$2;', money, other.id
        )
        await ctx.send(
            _(
                "Successfully gave **${money}** without a loss for you to **{other}**."
            ).format(money=money, other=other)
        )

        with handle_message_parameters(
                content="**{gm}** gave **${money}** to **{other}**.\n\nReason: *{reason}*".format(
                    gm=ctx.author,
                    money=money,
                    other=other,
                    reason=reason or f"<{ctx.message.jump_url}>",
                )
        ) as params:
            await self.bot.http.send_message(
                self.bot.config.game.gm_log_channel,
                params=params,
            )

    @is_gm()
    @commands.command(hidden=True, brief=_("Remove money"))
    @locale_doc
    async def gmremove(
            self,
            ctx,
            money: int,
            other: UserWithCharacter,
            *,
            reason: str = None,
    ):
        _(
            """`<money>` - the amount of money to remove from the user
            `<other>` - a discord User with character
            `[reason]` - The reason this action was done, defaults to the command message link

            Removes money from a user without adding it to the command author's balance.

            Only Game Masters can use this command."""
        )
        await self.bot.pool.execute(
            'UPDATE profile SET "money"="money"-$1 WHERE "user"=$2;', money, other.id
        )
        await ctx.send(
            _("Successfully removed **${money}** from **{other}**.").format(
                money=money, other=other
            )
        )

        with handle_message_parameters(
                content="**{gm}** removed **${money}** from **{other}**.\n\nReason: *{reason}*".format(
                    gm=ctx.author,
                    money=money,
                    other=other,
                    reason=reason or f"<{ctx.message.jump_url}>",
                )
        ) as params:
            await self.bot.http.send_message(
                self.bot.config.game.gm_log_channel,
                params=params,
            )

    @is_gm()
    @commands.command(hidden=True, brief=_("Delete a character"))
    @locale_doc
    async def gmdelete(self, ctx, other: UserWithCharacter, *, reason: str = None):
        _(
            """`<other>` - a discord User with character
            `[reason]` - The reason this action was done, defaults to the command message link

            Delete a user's profile. The user cannot be a Game Master.

            Only Game Masters can use this command."""
        )
        if other.id in ctx.bot.config.game.game_masters:  # preserve deletion of admins
            return await ctx.send(_("Very funny..."))
        async with self.bot.pool.acquire() as conn:
            g = await conn.fetchval(
                'DELETE FROM guild WHERE "leader"=$1 RETURNING id;', other.id
            )
            if g:
                await conn.execute(
                    'UPDATE profile SET "guildrank"=$1, "guild"=$2 WHERE "guild"=$3;',
                    "Member",
                    0,
                    g,
                )
                await conn.execute('UPDATE city SET "owner"=1 WHERE "owner"=$1;', g)
            partner = await conn.fetchval(
                'UPDATE profile SET "marriage"=$1 WHERE "marriage"=$2 RETURNING'
                ' "user";',
                0,
                other.id,
            )
            await conn.execute(
                'UPDATE children SET "mother"=$1, "father"=0 WHERE ("father"=$1 AND'
                ' "mother"=$2) OR ("father"=$2 AND "mother"=$1);',
                partner,
                other.id,
            )
            await self.bot.delete_profile(other.id, conn=conn)
        await ctx.send(_("Successfully deleted the character."))

        with handle_message_parameters(
                content="**{gm}** deleted **{other}**.\n\nReason: *{reason}*".format(
                    gm=ctx.author, other=other, reason=reason or f"<{ctx.message.jump_url}>"
                )
        ) as params:
            await self.bot.http.send_message(
                self.bot.config.game.gm_log_channel,
                params=params,
            )

    @is_gm()
    @commands.command(hidden=True, brief=_("Rename a character"))
    @locale_doc
    async def gmrename(self, ctx, target: UserWithCharacter, *, reason: str = None):
        _(
            """`<target>` - a discord User with character
            `[reason]` - The reason this action was done, defaults to the command message link

            Rename a user's profile. The user cannot be a Game Master.

            Only Game Masters can use this command."""
        )
        if target.id in ctx.bot.config.game.game_masters:  # preserve renaming of admins
            return await ctx.send(_("Very funny..."))

        await ctx.send(
            _("What shall the character's name be? (min. 3 letters, max. 20)")
        )

        def mycheck(amsg):
            return (
                    amsg.author == ctx.author
                    and amsg.channel == ctx.channel
                    and len(amsg.content) < 21
                    and len(amsg.content) > 2
            )

        try:
            name = await self.bot.wait_for("message", timeout=60, check=mycheck)
        except asyncio.TimeoutError:
            return await ctx.send(_("Timeout expired."))

        await self.bot.pool.execute(
            'UPDATE profile SET "name"=$1 WHERE "user"=$2;', name.content, target.id
        )
        await ctx.send(_("Renamed."))

        with handle_message_parameters(
                content="**{gm}** renamed **{target}** to **{name}**.\n\nReason: *{reason}*".format(
                    gm=ctx.author,
                    target=target,
                    name=name.content,
                    reason=reason or f"<{ctx.message.jump_url}>",
                )
        ) as params:
            await self.bot.http.send_message(
                self.bot.config.game.gm_log_channel,
                params=params,
            )

    @is_gm()
    @commands.command(hidden=True, brief=_("Create an item"))
    @locale_doc
    async def gmitem(
            self,
            ctx,
            stat: int,
            owner: UserWithCharacter,
            item_type: str.title,
            value: IntFromTo(0, 100000000),
            name: str,
            *,
            reason: str = None,
    ):
        _(
            """`<stat>` - the generated item's stat, must be between 0 and 100
            `<owner>` - a discord User with character
            `<item_type>` - the generated item's type, must be either Sword, Shield, Axe, Wand, Dagger, Knife, Spear, Bow, Hammer, Scythe or Howlet
            `<value>` - the generated item's value, a whole number from 0 to 100,000,000
            `<name>` - the generated item's name, should be in double quotes if the name has multiple words
            `[reason]` - The reason this action was done, defaults to the command message link

            Generate a custom item for a user.

            Only Game Masters can use this command."""
        )
        item_type = ItemType.from_string(item_type)
        if item_type is None:
            return await ctx.send(_("Invalid item type."))
        if not 0 <= stat <= 100:
            return await ctx.send(_("Invalid stat."))
        hand = item_type.get_hand().value
        await self.bot.create_item(
            name=name,
            value=value,
            type_=item_type.value,
            damage=stat if item_type != ItemType.Shield else 0,
            armor=stat if item_type == ItemType.Shield else 0,
            hand=hand,
            owner=owner,
        )

        message = "{gm} created a {item_type} with name {name} and stat {stat}.\n\nReason: *{reason}*".format(
            gm=ctx.author,
            item_type=item_type.value,
            name=name,
            stat=stat,
            reason=reason or f"<{ctx.message.jump_url}>",
        )

        await ctx.send(_("Done."))

        with handle_message_parameters(content=message) as params:
            await self.bot.http.send_message(
                self.bot.config.game.gm_log_channel, params=params
            )

        for user in self.bot.owner_ids:
            user = await self.bot.get_user_global(user)
            await user.send(message)

    @is_gm()
    @commands.command(hidden=True, brief=_("Create crates"))
    @locale_doc
    async def gmcrate(
            self,
            ctx,
            rarity: CrateRarity,
            amount: int,
            target: UserWithCharacter,
            *,
            reason: str = None,
    ):
        _(
            """`<rarity>` - the crates' rarity, can be common, uncommon, rare, magic or legendary
            `<amount>` - the amount of crates to generate for the given user, can be negative
            `<target>` - A discord User with character
            `[reason]` - The reason this action was done, defaults to the command message link

            Generate a set amount of crates of one rarity for a user.

            Only Game Masters can use this command."""
        )
        await self.bot.pool.execute(
            f'UPDATE profile SET "crates_{rarity}"="crates_{rarity}"+$1 WHERE'
            ' "user"=$2;',
            amount,
            target.id,
        )
        await ctx.send(
            _("Successfully gave **{amount}** {rarity} crates to **{target}**.").format(
                amount=amount, target=target, rarity=rarity
            )
        )

        with handle_message_parameters(
                content="**{gm}** gave **{amount}** {rarity} crates to **{target}**.\n\nReason: *{reason}*".format(
                    gm=ctx.author,
                    amount=amount,
                    rarity=rarity,
                    target=target,
                    reason=reason or f"<{ctx.message.jump_url}>",
                )
        ) as params:
            await self.bot.http.send_message(
                self.bot.config.game.gm_log_channel,
                params=params,
            )

    @is_gm()
    @commands.command(hidden=True, brief=_("Generate XP"))
    @locale_doc
    async def gmxp(
            self,
            ctx,
            target: UserWithCharacter,
            amount: int,
            *,
            reason: str = None,
    ):
        _(
            """`<target>` - A discord User with character
            `<amount>` - The amount of XP to generate, can be negative
            `[reason]` - The reason this action was done, defaults to the command message link

            Generates a set amount of XP for a user.

            Only Game Masters can use this command."""
        )
        await self.bot.pool.execute(
            'UPDATE profile SET "xp"="xp"+$1 WHERE "user"=$2;', amount, target.id
        )
        await ctx.send(
            _("Successfully gave **{amount}** XP to **{target}**.").format(
                amount=amount, target=target
            )
        )

        with handle_message_parameters(
                content="**{gm}** gave **{amount}** XP to **{target}**.\n\nReason: *{reason}*".format(
                    gm=ctx.author,
                    amount=amount,
                    target=target,
                    reason=reason or f"<{ctx.message.jump_url}>",
                )
        ) as params:
            await self.bot.http.send_message(
                self.bot.config.game.gm_log_channel,
                params=params,
            )

    @is_gm()
    @commands.command(hidden=True, brief=_("Wipe someone's donation perks."))
    @locale_doc
    async def gmwipeperks(self, ctx, target: UserWithCharacter, *, reason: str = None):
        _(
            """`<target>` - A discord User with character
            `[reason]` - The reason this action was done, defaults to the command message link

            Wipe a user's donation perks. This will:
              - set their background to the default
              - set both their classes to No Class
              - reverts all items to their original type and name
              - sets their guild's member limit to 50

            Only Game Masters can use this command."""
        )
        async with self.bot.pool.acquire() as conn:
            await conn.execute(
                'UPDATE profile SET "background"=$1, "class"=$2 WHERE "user"=$3;',
                "0",
                ["No Class", "No Class"],
                target.id,
            )
            await conn.execute(
                'UPDATE allitems SET "name"=CASE WHEN "original_name" IS NULL THEN'
                ' "name" ELSE "original_name" END, "type"=CASE WHEN "original_type" IS'
                ' NULL THEN "type" ELSE "original_type" END WHERE "owner"=$1;',
                target.id,
            )
            await conn.execute(
                'UPDATE guild SET "memberlimit"=$1 WHERE "leader"=$2;', 50, target.id
            )

        await ctx.send(
            _(
                "Successfully reset {target}'s background, class, item names and guild"
                " member limit."
            ).format(target=target)
        )

        with handle_message_parameters(
                content="**{gm}** reset **{target}**'s donator perks.\n\nReason: *{reason}*".format(
                    gm=ctx.author,
                    target=target,
                    reason=reason or f"<{ctx.message.jump_url}>",
                )
        ) as params:
            await self.bot.http.send_message(
                self.bot.config.game.gm_log_channel,
                params=params,
            )

    @is_gm()
    @commands.command(hidden=True, brief=_("Reset someone's classes"))
    @locale_doc
    async def gmresetclass(self, ctx, target: UserWithCharacter, *, reason: str = None):
        _(
            """`<target>` - a discord User with character
            `[reason]` - The reason this action was done, defaults to the command message link

            Reset a user's classes to No Class. They can then choose their class again for free.

            Only Game Masters can use this command."""
        )
        await self.bot.pool.execute(
            """UPDATE profile SET "class"='{"No Class", "No Class"}' WHERE "user"=$1;""",
            target.id,
        )

        await ctx.send(_("Successfully reset {target}'s class.").format(target=target))

        with handle_message_parameters(
                content="**{gm}** reset **{target}**'s class.\n\nReason: *{reason}*".format(
                    gm=ctx.author,
                    target=target,
                    reason=reason or f"<{ctx.message.jump_url}>",
                )
        ) as params:
            await self.bot.http.send_message(
                self.bot.config.game.gm_log_channel,
                params=params,
            )

    @is_gm()
    @user_cooldown(604800)  # 7 days
    @commands.command(hidden=True, brief=_("Sign an item"))
    @locale_doc
    async def gmsign(self, ctx, itemid: int, text: str, *, reason: str = None):
        _(
            """`<itemid>` - the item's ID to sign
            `<text>` - The signature to write, must be less than 50 characters combined with the Game Master's tag. This should be in double quotes if the text has multiple words.
            `[reason]` - The reason this action was done, defaults to the command message link

            Sign an item. The item's signature is visible in a user's inventory.

            Only Game Masters can use this command.
            (This command has a cooldown of 7 days.)"""
        )
        text = f"{text} (signed by {ctx.author})"
        if len(text) > 50:
            await self.bot.reset_cooldown(ctx)
            return await ctx.send(_("Text exceeds 50 characters."))
        await self.bot.pool.execute(
            'UPDATE allitems SET "signature"=$1 WHERE "id"=$2;', text, itemid
        )
        await ctx.send(_("Item successfully signed."))

        with handle_message_parameters(
                content="**{gm}** signed {itemid} with *{text}*.\n\nReason: *{reason}*".format(
                    gm=ctx.author,
                    itemid=itemid,
                    text=text,
                    reason=reason or f"<{ctx.message.jump_url}>",
                )
        ) as params:
            await self.bot.http.send_message(
                self.bot.config.game.gm_log_channel,
                params=params,
            )

    def load_patron_ids(self):
        try:
            with open("patron_ids.json", "r") as file:
                return json.load(file)
        except FileNotFoundError:
            return []

    def save_patron_ids(self):
        with open("patron_ids.json", "w") as file:
            json.dump(self.patron_ids, file)

    def add_patron(self, user_id: int):
        if user_id not in self.patron_ids:
            self.patron_ids.append(user_id)
            self.save_patron_ids()  # Save updated patron IDs
            return True
        else:
            return False

    def remove_patron(self, user_id: int):
        if user_id in self.patron_ids:
            self.patron_ids.remove(user_id)
            self.save_patron_ids()  # Save updated patron IDs
            return True
        else:
            return False

    @is_gm()
    @commands.command(hidden=True, brief=_("Add Patreon"))
    async def add_patron(self, ctx, user_id: int):
        """Add a patron by their user ID."""
        if user_id not in self.patron_ids:
            self.patron_ids.append(user_id)
            self.save_patron_ids()  # Use self to access the method
            await ctx.send(f"User with ID {user_id} has been added as a patron.")
        else:
            await ctx.send(f"User with ID {user_id} is already a patron.")

    @is_gm()
    @commands.command(hidden=True, brief=_("Remove Patreon"))
    async def remove_patron(self, ctx, user_id: int):
        """Remove a patron by their user ID."""
        if self.remove_patron(user_id):
            await ctx.send(f"User with ID {user_id} has been removed as a patron.")
        else:
            await ctx.send(f"User with ID {user_id} is not a patron.")

    @is_gm()
    @commands.command(hidden=True, brief=_("Start an auction"))
    @locale_doc
    async def gmauction(self, ctx, *, item: str):
        _(
            """`<item>` - a description of what is being auctioned

            Starts an auction on the support server. Users are able to bid. The auction timeframe extends by 30 minutes if users keep betting.
            The auction ends when no user bids in a 30 minute timeframe.

            The item is not given automatically and the needs to be given manually.

            Only Game Masters can use this command."""
        )
        if self.top_auction is not None:
            return await ctx.send(_("There's still an auction running."))
        try:
            channel = discord.utils.get(
                self.bot.get_guild(self.bot.config.game.support_server_id).channels,
                name="auctions",
            )
        except AttributeError:
            return await ctx.send(_("Auctions channel wasn't found."))
        await channel.send(
            f"{ctx.author.mention} started auction on **{item}**! Please use"
            f" `{ctx.clean_prefix}bid amount` to raise the bid. If no more bids are sent"
            " within a 30 minute timeframe, the auction is over."
        )
        self.top_auction = (ctx.author, 0)
        timer = 60 * 30
        self.auction_entry = asyncio.Event()
        try:
            while True:
                async with asyncio.timeout(timer):
                    await self.auction_entry.wait()
                    self.auction_entry.clear()
        except asyncio.TimeoutError:
            pass
        await channel.send(
            f"**{item}** sold to {self.top_auction[0].mention} for"
            f" **${self.top_auction[1]}**!"
        )
        self.top_auction = None
        self.auction_entry = None

    @has_char()
    @commands.command(hidden=True, brief=_("Bid on an auction"))
    @locale_doc
    async def bid(self, ctx, amount: IntGreaterThan(0)):
        _(
            """`<amount>` - the amount of money to bid, must be higher than the current highest bid

            Bid on an ongoing auction.

            The amount is removed from you as soon as you bid and given back if someone outbids you. This is to prevent bidding impossibly high and then not paying up."""
        )
        if self.top_auction is None:
            return await ctx.send(_("No auction running."))
        if amount <= self.top_auction[1]:
            return await ctx.send(_("Bid too low."))
        if ctx.character_data["money"] < amount:
            return await ctx.send(_("You are too poor."))
        async with self.bot.pool.acquire() as conn:
            await conn.execute(
                'UPDATE profile SET "money"="money"+$1 WHERE "user"=$2;',
                self.top_auction[1],
                self.top_auction[0].id,
            )
            await self.bot.log_transaction(
                ctx,
                from_=1,
                to=self.top_auction[0].id,
                subject="bid",
                data={"Amount": self.top_auction[1]},
                conn=conn,
            )
            self.top_auction = (ctx.author, amount)
            self.auction_entry.set()
            await conn.execute(
                'UPDATE profile SET "money"="money"-$1 WHERE "user"=$2;',
                amount,
                ctx.author.id,
            )
            await self.bot.log_transaction(
                ctx,
                from_=ctx.author.id,
                to=2,
                subject="bid",
                data={"Amount": amount},
                conn=conn,
            )
        await ctx.send(_("Bid submitted."))
        channel = discord.utils.get(
            self.bot.get_guild(self.bot.config.game.support_server_id).channels,
            name="auctions",
        )
        await channel.send(
            f"**{ctx.author.mention}** bids **${amount}**! Check above for what's being"
            " auctioned."
        )

    @is_gm()
    @commands.command(
        aliases=["gmcd", "gmsetcd"], hidden=True, brief=_("Set a cooldown")
    )
    @locale_doc
    async def gmsetcooldown(
            self,
            ctx,
            user: discord.User | int,
            command: str,
            *,
            reason: str = None,
    ):
        _(
            """`<user>` - A discord User or their User ID
            `<command>` - the command which the cooldown is being set for (subcommands in double quotes, i.e. "guild create")
            `[reason]` - The reason this action was done, defaults to the command message link

            Reset a cooldown for a user and commmand.

            Only Game Masters can use this command."""
        )
        if not isinstance(user, int):
            user_id = user.id
        else:
            user_id = user

        result = await self.bot.redis.execute_command("DEL", f"cd:{user_id}:{command}")

        if result == 1:
            await ctx.send(_("The cooldown has been updated!"))

            with handle_message_parameters(
                    content="**{gm}** reset **{user}**'s cooldown for the {command} command.\n\nReason: *{reason}*".format(
                        gm=ctx.author,
                        user=user,
                        command=command,
                        reason=reason or f"<{ctx.message.jump_url}>",
                    )
            ) as params:
                await self.bot.http.send_message(
                    self.bot.config.game.gm_log_channel,
                    params=params,
                )
        else:
            await ctx.send(
                _(
                    "Cooldown setting unsuccessful (maybe you mistyped the command name"
                    " or there is no cooldown for the user?)."
                )
            )

    @is_gm()
    @commands.command(
        aliases=["gmml", "gmluck"],
        hidden=True,
        brief=_("Update the luck for all followers"),
    )
    @locale_doc
    async def gmmakeluck(self, ctx) -> None:
        _(
            """Sets the luck for all gods to a random value and give bonus luck to the top 25 followers.

            Only Game Masters can use this command."""
        )
        text_collection = ["**This week's luck has been decided:**\n"]
        all_ids = []
        async with self.bot.pool.acquire() as conn:
            for god in self.bot.config.gods:
                luck = (
                        random.randint(
                            god["boundary_low"] * 100, god["boundary_high"] * 100
                        )
                        / 100
                )
                ids = await conn.fetch(
                    'UPDATE profile SET "luck"=round($1, 2) WHERE "god"=$2 RETURNING'
                    ' "user";',
                    luck,
                    god["name"],
                )
                all_ids.extend([u["user"] for u in ids])
                top_followers = [
                    u["user"]
                    for u in await conn.fetch(
                        'SELECT "user" FROM profile WHERE "god"=$1 ORDER BY "favor"'
                        " DESC LIMIT 25;",
                        god["name"],
                    )
                ]
                await conn.execute(
                    'UPDATE profile SET "luck"=CASE WHEN "luck"+round($1, 2)>=2.0 THEN'
                    ' 2.0 ELSE "luck"+round($1, 2) END WHERE "user"=ANY($2);',
                    0.5,
                    top_followers[:5],
                )
                await conn.execute(
                    'UPDATE profile SET "luck"=CASE WHEN "luck"+round($1, 2)>=2.0 THEN'
                    ' 2.0 ELSE "luck"+round($1, 2) END WHERE "user"=ANY($2);',
                    0.4,
                    top_followers[5:10],
                )
                await conn.execute(
                    'UPDATE profile SET "luck"=CASE WHEN "luck"+round($1, 2)>=2.0 THEN'
                    ' 2.0 ELSE "luck"+round($1, 2) END WHERE "user"=ANY($2);',
                    0.3,
                    top_followers[10:15],
                )
                await conn.execute(
                    'UPDATE profile SET "luck"=CASE WHEN "luck"+round($1, 2)>=2.0 THEN'
                    ' 2.0 ELSE "luck"+round($1, 2) END WHERE "user"=ANY($2);',
                    0.2,
                    top_followers[15:20],
                )
                await conn.execute(
                    'UPDATE profile SET "luck"=CASE WHEN "luck"+round($1, 2)>=2.0 THEN'
                    ' 2.0 ELSE "luck"+round($1, 2) END WHERE "user"=ANY($2);',
                    0.1,
                    top_followers[20:25],
                )
                text_collection.append(f"{god['name']} set to {luck}.")
            await conn.execute('UPDATE profile SET "favor"=0 WHERE "god" IS NOT NULL;')
            text_collection.append("Godless set to 1.0")
            ids = await conn.fetch(
                'UPDATE profile SET "luck"=1.0 WHERE "god" IS NULL RETURNING "user";'
            )
            all_ids.extend([u["user"] for u in ids])
        await ctx.send("\n".join(text_collection))

        with handle_message_parameters(
                content=f"**{ctx.author}** updated the global luck"
        ) as params:
            await self.bot.http.send_message(
                self.bot.config.game.gm_log_channel,
                params=params,
            )

    def cleanup_code(self, content: str) -> str:
        """Automatically removes code blocks from the code."""
        if content.startswith("```") and content.endswith("```"):
            return "\n".join(content.split("\n")[1:-1])
        return content.strip("` \n")

    @is_gm()
    @commands.command(hidden=True, name="eval")
    async def _eval(self, ctx: Context, *, body: str) -> None:
        """Evaluates a code"""

        env = {
            "bot": self.bot,
            "ctx": ctx,
            "channel": ctx.channel,
            "author": ctx.author,
            "guild": ctx.guild,
            "message": ctx.message,
            "__last__": self._last_result,
        }

        env.update(globals())

        body = self.cleanup_code(body)
        stdout = io.StringIO()
        token = random_token(self.bot.user.id)

        to_compile = f'async def func():\n{textwrap.indent(body, "  ")}'

        try:
            exec(to_compile, env)
        except Exception as e:
            return await ctx.send(f"```py\n{e.__class__.__name__}: {e}\n```")

        func = env["func"]
        try:
            with redirect_stdout(stdout):
                ret = await func()
            if ret is not None:
                ret = str(ret).replace(self.bot.http.token, token)
        except Exception:
            value = stdout.getvalue()
            value = value.replace(self.bot.http.token, token)
            await ctx.send(f"```py\n{value}{traceback.format_exc()}\n```")
        else:
            value = stdout.getvalue()
            value = value.replace(self.bot.http.token, token)
            try:
                await ctx.message.add_reaction("blackcheck:441826948919066625")
            except discord.Forbidden:
                pass

            if ret is None:
                if value:
                    await ctx.send(f"```py\n{value}\n```")
            else:
                self._last_result = ret
                await ctx.send(f"```py\n{value}{ret}\n```")

    @is_gm()
    @commands.command(hidden=True)
    async def evall(self, ctx: Context, *, code: str) -> None:
        """[Owner only] Evaluates python code on all processes."""
        data = await self.bot.cogs["Sharding"].handler(
            "evaluate", self.bot.shard_count, {"code": code}
        )
        filtered_data = {instance: data.count(instance) for instance in data}
        pretty_data = "".join(
            f"```py\n{count}x | {instance[6:]}"
            for instance, count in filtered_data.items()
        )
        if len(pretty_data) > 2000:
            pretty_data = pretty_data[:1997] + "..."
        await ctx.send(pretty_data)

    @commands.command(hidden=True)
    async def bash(self, ctx: Context, *, command_to_run: str) -> None:
        """[Owner Only] Run shell commands."""
        await shell.run(command_to_run, ctx)

    @is_gm()
    @commands.command(hidden=True)
    async def runas(
            self, ctx: Context, member: discord.Member, *, command: str
    ) -> None:
        """[Owner Only] Run a command as if you were the user."""
        fake_msg = copy.copy(ctx.message)
        fake_msg._update(dict(channel=ctx.channel, content=ctx.clean_prefix + command))
        fake_msg.author = member
        new_ctx = await ctx.bot.get_context(fake_msg)
        try:
            await ctx.bot.invoke(new_ctx)
        except Exception:
            await ctx.send(f"```py\n{traceback.format_exc()}```")

    def replace_md(self, s):
        opening = True
        out = []
        for i in s:
            if i == "`":
                if opening is True:
                    opening = False
                    i = "<code>"
                else:
                    opening = True
                    i = "</code>"
            out.append(i)
        reg = re.compile(r'\[(.+)\]\(([^ ]+?)( "(.+)")?\)')
        text = "".join(out)
        text = re.sub(reg, r'<a href="\2">\1</a>', text)
        reg = re.compile(r"~~(.+)~~")
        text = re.sub(reg, r"<s>\1</s>", text)
        reg = re.compile(r"__(.+)__")
        text = re.sub(reg, r"<u>\1</u>", text)
        reg = re.compile(r"\*\*(.+)\*\*")
        text = re.sub(reg, r"<b>\1</b>", text)
        reg = re.compile(r"\*(.+)\*")
        text = re.sub(reg, r"<i>\1</i>", text)
        return text

    def make_signature(self, cmd):
        if cmd.aliases:
            prelude = cmd.qualified_name.replace(cmd.name, "").strip()
            if prelude:
                prelude = f"{prelude} "
            actual_names = cmd.aliases + [cmd.name]
            aliases = f"{prelude}[{'|'.join(actual_names)}]"
        else:
            aliases = cmd.qualified_name
        return f"${aliases} {cmd.signature}"

    @is_gm()
    @commands.command(hidden=True)
    async def makehtml(self, ctx: Context) -> None:
        """Generates HTML for commands page."""
        with open("assets/html/commands.html") as f:
            base = f.read()
        with open("assets/html/cog.html") as f:
            cog = f.read()
        with open("assets/html/command.html") as f:
            command = f.read()

        html = ""

        for cog_name, cog_ in self.bot.cogs.items():
            if cog_name in ("GameMaster", "Owner", "Custom"):
                continue
            commands = {c for c in list(cog_.walk_commands()) if not c.hidden}
            if len(commands) > 0:
                html += cog.format(name=cog_name)
                for cmd in commands:
                    html += command.format(
                        name=cmd.qualified_name,
                        usage=self.make_signature(cmd)
                        .replace("<", "&lt;")
                        .replace(">", "&gt;"),
                        checks=f"<b>Checks: {checks}</b>"
                        if (
                            checks := ", ".join(
                                [
                                    (
                                        "cooldown"
                                        if "cooldown" in name
                                        else (
                                            "has_character"
                                            if name == "has_char"
                                            else name
                                        )
                                    )
                                    for c in cmd.checks
                                    if (
                                           name := re.search(
                                               r"<function ([^.]+)\.", repr(c)
                                           ).group(1)
                                       )
                                       != "update_pet"
                                ]
                            )
                        )
                        else "",
                        description=self.replace_md(
                            (cmd.help or "No Description Set")
                            .format(prefix="$")
                            .replace("<", "&lt;")
                            .replace(">", "&gt;")
                        ).replace("\n", "<br>"),
                    )

        html = base.format(content=html)
        await ctx.send(
            file=discord.File(filename="commands.html", fp=io.StringIO(html))
        )

    @is_gm()
    @commands.group(hidden=True, invoke_without_command=True)
    async def badges(self, ctx: Context, user: UserWithCharacter) -> None:
        badges = Badge.from_db(ctx.user_data["badges"])

        if badges:
            await ctx.send(badges.to_pretty())
        else:
            await ctx.send("User has no badges")

    @is_gm()
    @badges.command(hidden=True, name="add")
    async def badges_add(
            self, ctx: Context, user: UserWithCharacter, badge: BadgeConverter
    ) -> None:
        badges = Badge.from_db(ctx.user_data["badges"])
        badges |= badge

        await self.bot.pool.execute(
            'UPDATE profile SET "badges"=$1 WHERE "user"=$2;', badges.to_db(), user.id
        )

        await ctx.send("Done")

    @is_gm()
    @badges.command(hidden=True, name="rem", aliases=["remove", "delete", "del"])
    async def badges_rem(
            self, ctx: Context, user: UserWithCharacter, badge: BadgeConverter
    ) -> None:
        badges = Badge.from_db(ctx.user_data["badges"])
        badges ^= badge

        await self.bot.pool.execute(
            'UPDATE profile SET "badges"=$1 WHERE "user"=$2;', badges.to_db(), user.id
        )

        await ctx.send("Done")


async def setup(bot):
    await bot.add_cog(GameMaster(bot))
