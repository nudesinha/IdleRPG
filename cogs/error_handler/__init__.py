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
import traceback

from asyncio import TimeoutError
from datetime import timedelta

import discord

from aiohttp import ClientOSError, ContentTypeError, ServerDisconnectedError
from asyncpg.exceptions import DataError as AsyncpgDataError
from discord.ext import commands

import utils.checks

from classes.bot import Bot
from classes.classes import Ranger, get_class_evolves
from classes.context import Context
from classes.converters import (
    DateOutOfRange,
    InvalidCoinSide,
    InvalidCrateRarity,
    InvalidTime,
    InvalidUrl,
    NotInRange,
    UserHasNoChar,
)
from classes.errors import NoChoice
from classes.exceptions import GlobalCooldown
from utils.i18n import _

try:
    import sentry_sdk
except ModuleNotFoundError:
    SENTRY_AVAILABLE = False
else:
    SENTRY_AVAILABLE = True


def before_send(event, hint):
    if "exc_info" in hint:
        _exc_type, exc_value, _tb = hint["exc_info"]
        if isinstance(exc_value, (discord.HTTPException, TimeoutError)):
            return None
    return event


class Errorhandler(commands.Cog):
    def __init__(self, bot: Bot) -> None:
        self.bot = bot
        bot.on_command_error = self._on_command_error
        sentry_url = self.bot.config.statistics.sentry_url
        self.SENTRY_SUPPORT = SENTRY_AVAILABLE and sentry_url is not None
        if self.SENTRY_SUPPORT:
            sentry_sdk.init(sentry_url, before_send=before_send)

    async def _on_command_error(
        self, ctx: Context, error: Exception, bypass: bool = False
    ) -> None:
        if (
            hasattr(ctx.command, "on_error")
            or (ctx.command and hasattr(ctx.cog, f"_{ctx.command.cog_name}__error"))
            and not bypass
        ):
            # Do nothing if the command/cog has its own error handler
            return
        if isinstance(error, commands.CommandNotFound):
            return
        elif isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(
                _("Oops! You forgot a required argument: `{arg}`").format(
                    arg=error.param.name
                )
            )
        elif isinstance(error, commands.BadArgument):
            if isinstance(error, commands.MessageNotFound):
                await ctx.send(_("The message you referenced was not found."))
            elif isinstance(error, commands.MemberNotFound):
                await ctx.send(_("The member you referenced was not found."))
            elif isinstance(error, commands.GuildNotFound):
                await ctx.send(_("The server you referenced was not found."))
            elif isinstance(error, commands.UserNotFound):
                await ctx.send(_("The user you referenced was not found."))
            elif isinstance(error, commands.ChannelNotFound):
                await ctx.send(_("The channel you referenced was not found."))
            elif isinstance(error, commands.ChannelNotReadable):
                await ctx.send(
                    _("I cannot read messages in the channel you referenced.")
                )
            elif isinstance(error, commands.BadColourArgument):
                await ctx.send(_("I could not parse a colour from this."))
            elif isinstance(error, commands.RoleNotFound):
                await ctx.send(_("The role you referenced was not found."))
            elif isinstance(error, commands.BadInviteArgument):
                await ctx.send(
                    _("The invite you referenced is invalid or has expired.")
                )
            elif isinstance(error, commands.EmojiNotFound):
                await ctx.send(_("The emoji you referenced was not found."))
            elif isinstance(error, commands.BadBoolArgument):
                await ctx.send(_("I could not parse a boolean from this."))
            elif isinstance(error, NotInRange):
                await ctx.send(error.text)
            elif isinstance(error, UserHasNoChar):
                await ctx.send(
                    _(
                        "The user you specified as a parameter does not have a"
                        " character."
                    )
                )
            elif isinstance(error, InvalidCrateRarity):
                await ctx.send(
                    _(
                        "You did not enter a valid crate rarity. Possible ones are:"
                        " common (c), uncommon (u), rare (r), magic (m), legendary (l) and mystery (myst)."
                    )
                )
            elif isinstance(error, InvalidCoinSide):
                await ctx.send(
                    _(
                        "You did not enter a valid coin side. Please use `heads` or"
                        " `tails`."
                    )
                )
            elif isinstance(error, DateOutOfRange):
                await ctx.send(
                    _(
                        "You entered a date that was out of range. It should be newer"
                        " than {date}."
                    ).format(date=error.min_)
                )
            elif isinstance(error, InvalidTime):
                await ctx.send(error.text)
            elif isinstance(error, InvalidUrl):
                await ctx.send(
                    _(
                        "You sent an invalid URL. Make sure to send the full URL; it"
                        ' should start with "http" and end with ".png" or ".jpeg".'
                    )
                )
            else:
                await ctx.send(_("You used a malformed argument!"))
        elif isinstance(error, GlobalCooldown):
            return await ctx.send(
                _(
                    "You are being rate-limited. Chill down, you can use a command"
                    " again in {time}s."
                ).format(time=round(error.retry_after, 2))
            )
        elif isinstance(error, commands.CommandOnCooldown):
            return await ctx.send(
                _("You are on cooldown. Try again in {time}.").format(
                    time=timedelta(seconds=int(error.retry_after))
                )
            )
        elif hasattr(error, "original") and isinstance(
            error.original, discord.HTTPException
        ):
            return  # not our fault
        elif isinstance(error, commands.NotOwner):
            await ctx.send(
                embed=discord.Embed(
                    title=_("Permission denied"),
                    description=_(
                        ":x: This command is only avaiable for the bot owner."
                    ),
                    colour=0xFF0000,
                )
            )
        elif isinstance(error, commands.CheckFailure):
            if isinstance(error, utils.checks.NoCharacter):
                await ctx.send(_("You don't have a character yet."))
            elif isinstance(error, utils.checks.NeedsNoCharacter):
                await ctx.send(
                    _(
                        "This command requires you to not have created a character yet."
                        " You already have one."
                    )
                )
            elif isinstance(error, utils.checks.NeedsGod):
                await ctx.send(
                    _(
                        "You need to be following a god for this command. Please use"
                        " `{prefix}follow` to choose one."
                    ).format(prefix=ctx.clean_prefix)
                )
            elif isinstance(error, utils.checks.NoGuild):
                await ctx.send(_("You need to have a guild to use this command."))
            elif isinstance(error, utils.checks.NeedsNoGuild):
                await ctx.send(_("You need to be in no guild to use this command."))
            elif isinstance(error, utils.checks.NoGuildPermissions):
                await ctx.send(
                    _("Your rank in the guild is too low to use this command.")
                )
            elif isinstance(error, utils.checks.NeedsNoGuildLeader):
                await ctx.send(
                    _("You mustn't be the owner of a guild to use this command.")
                )
            elif isinstance(error, utils.checks.WrongClass):
                await ctx.send(
                    embed=discord.Embed(
                        title=_("Permission denied"),
                        description=_(
                            ":x: You don't have the permissions to use this command. It"
                            " is thought for {error} class users."
                        ).format(error=error),
                        colour=0xFF0000,
                    )
                )
            elif isinstance(error, utils.checks.NeedsNoAdventure):
                await ctx.send(
                    _(
                        "You are already on an adventure. Use `{prefix}status` to see"
                        " how long it lasts."
                    ).format(prefix=ctx.clean_prefix)
                )
            elif isinstance(error, utils.checks.NeedsAdventure):
                await ctx.send(
                    _(
                        "You need to be on an adventure to use this command. Try"
                        " `{prefix}adventure`!"
                    ).format(prefix=ctx.clean_prefix)
                )
            elif isinstance(error, utils.checks.PetGone):
                await ctx.send(
                    _(
                        "Your pet has gone missing. Maybe some aliens abducted it?"
                        " Since you can't find it anymore, you are no longer a"
                        " {profession}"
                    ).format(profession=_("Ranger"))
                )
                classes = ctx.character_data["class"]
                for evolve in get_class_evolves(Ranger):
                    name = evolve.class_name()
                    if name in classes:
                        idx = classes.index(name)
                        break
                classes[idx] = "No Class"
                await self.bot.pool.execute(
                    'UPDATE profile SET "class"=$1 WHERE "user"=$2;',
                    classes,
                    ctx.author.id,
                )
            elif isinstance(error, utils.checks.PetDied):
                await ctx.send(
                    _(
                        "Your pet **{pet}** died! You did not give it enough to eat or"
                        " drink. Because of your bad treatment, you are no longer a"
                        " {profession}."
                    ).format(pet=ctx.pet_data["name"], profession=_("Ranger"))
                )
            elif isinstance(error, utils.checks.PetRanAway):
                await ctx.send(
                    _(
                        "Your pet **{pet}** ran away! You did not show it your love"
                        " enough! Because of your bad treatment, you are no longer a"
                        " {profession}."
                    ).format(pet=ctx.pet_data["name"], profession=_("Ranger"))
                )
            elif isinstance(error, utils.checks.NoPatron):
                await ctx.send(
                    _(
                        "You need to be a {tier} tier donator to use this command."
                        " Please head to `{prefix}donate` and make sure you joined the"
                        " support server if you decide to support us."
                    ).format(tier=error.tier.name.title(), prefix=ctx.clean_prefix)
                )
            elif isinstance(error, utils.checks.AlreadyRaiding):
                await ctx.send(
                    _(
                        "There is another raid already ongoing. Try again at a later"
                        " time."
                    )
                )
            elif isinstance(error, utils.checks.NoCityOwned):
                await ctx.send(_("Your alliance does not own a city."))
            elif isinstance(error, utils.checks.CityOwned):
                await ctx.send(_("Your alliance already owns a city."))
            elif isinstance(error, utils.checks.NoAlliancePermissions):
                await ctx.send(_("Your alliance rank is too low."))
            elif isinstance(error, utils.checks.NoOpenHelpRequest):
                await ctx.send(_("Your server does not have an open help request."))
            elif isinstance(error, utils.checks.ImgurUploadError):
                await ctx.send(
                    _(
                        "There was an error when uploading to Imgur. Please try again"
                        " or visit <https://imgur.com/upload> to manually upload your"
                        " image."
                    )
                )
            else:
                await ctx.send(
                    embed=discord.Embed(
                        title=_("Permission denied"),
                        description=_(
                            ":x: You don't have the permissions to use this command. It"
                            " is thought for other users."
                        ),
                        colour=0xFF0000,
                    )
                )
        elif isinstance(error, NoChoice):
            await ctx.send(_("You did not choose anything."))
        elif isinstance(error, commands.CommandInvokeError) and hasattr(
            error, "original"
        ):
            if isinstance(
                error.original,
                (
                    ClientOSError,
                    ServerDisconnectedError,
                    ContentTypeError,
                    TimeoutError,
                ),
            ):
                # Called on 500 HTTP responses
                # TimeoutError: A Discord operation timed out. All others should be handled by us
                return
            elif isinstance(error.original, AsyncpgDataError):
                return await ctx.send(
                    _(
                        "An argument or value you entered was far too high for me to"
                        " handle properly!"
                    )
                )
            elif isinstance(error.original, LookupError):
                await ctx.send(
                    _(
                        "The languages have been reloaded while you were using a"
                        " command. The execution therefore had to be stopped. Please"
                        " try again."
                    )
                )
            if not self.SENTRY_SUPPORT:
                tb = "\n".join(traceback.format_tb(error.original.__traceback__))
                self.bot.logger.error(f"In {ctx.command.qualified_name}: {tb}")
            else:
                try:
                    raise error.original
                except Exception as e:
                    if ctx.guild:
                        guild_id = ctx.guild.id
                    else:
                        guild_id = "None"
                    with sentry_sdk.push_scope() as scope:
                        scope.set_context("message", {"content": ctx.message.content})
                        scope.set_extra("guild_id", str(guild_id))
                        scope.set_extra("channel_id", str(ctx.channel.id))
                        scope.set_extra("message_id", str(ctx.message.id))
                        scope.set_extra("user_id", str(ctx.author.id))
                        scope.set_tag("command", ctx.command.qualified_name)
                        sentry_sdk.capture_exception(e)
                await ctx.send(
                    _(
                        "Reminder Set."
                    )
                )
        await ctx.bot.reset_cooldown(ctx)
        if ctx.command.parent:
            if ctx.command.root_parent.name == "guild" and hasattr(
                ctx, "character_data"
            ):
                await self.bot.reset_guild_cooldown(ctx)
            elif ctx.command.root_parent.name == "alliance":
                await self.bot.reset_alliance_cooldown(ctx)


async def setup(bot):
    await bot.add_cog(Errorhandler(bot))
