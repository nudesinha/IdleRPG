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
from collections import Counter, namedtuple

import discord
import random

from discord.ext import commands

from classes.converters import (
    CrateRarity,
    IntFromTo,
    IntGreaterThan,
    MemberWithCharacter,
)
from cogs.shard_communication import user_on_cooldown as user_cooldown
from utils import random
from utils.checks import has_char, has_money
from utils.i18n import _, locale_doc


class Crates(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.emotes = namedtuple(
            "CrateEmotes", "common uncommon rare magic legendary item mystery"
        )(
            common="<:F_common:1139514874016309260>",
            uncommon="<:F_uncommon:1139514875828252702>",
            rare="<:F_rare:1139514880517484666>",
            magic="<:F_Magic:1139514865174720532>",
            legendary="<:F_Legendary:1139514868400132116>",
            item="<a:ItemAni:896715561550110721>",
            mystery="<:F_mystspark:1139521536320094358>",
        )

    @has_char()
    @commands.command(aliases=["boxes"], brief=_("Show your crates."))
    @locale_doc
    async def crates(self, ctx):
        _(
            """Shows all the crates you can have.

            Common crates contain items ranging from stats 1 to 30
            Uncommon crates contain items ranging from stats 10 to 35
            Rare crates contain items ranging from stats 20 to 40
            Magic crates contain items ranging from stats 30 to 45
            Legendary crates contain items ranging from stats 41 to 50

            You can receive crates by voting for the bot using `{prefix}vote`, using `{prefix}daily` and with a small chance from `{prefix}familyevent`, if you have children."""
        )
        embed = discord.Embed(
            title=_("Your Crates"), color=discord.Color.blurple()
        ).set_author(name=ctx.disp, icon_url=ctx.author.display_avatar.url)

        for rarity in ("common", "uncommon", "rare", "magic", "legendary", "mystery"):
            amount = ctx.character_data[f"crates_{rarity}"]
            embed.add_field(
                name=f"{getattr(self.emotes, rarity)} {rarity.title()}",
                value=_("{amount} crates").format(amount=amount),
                inline=False,
            )

        embed.set_footer(
            text=_("Use {prefix}open [rarity] to open one!").format(
                prefix=ctx.clean_prefix
            )
        )

        await ctx.send(embed=embed)

    @commands.cooldown(1, 10, commands.BucketType.user)
    @has_char()
    @commands.command(name="open", brief=_("Open a crate"))
    @locale_doc
    async def _open(
            self, ctx, rarity: CrateRarity = "common", amount: IntFromTo(1, 100) = 1
    ):
        _(
            """`[rarity]` - the crate's rarity to open, can be common, uncommon, rare, magic or legendary; defaults to common
            `[amount]` - the amount of crates to open, may be in range from 1 to 100 at once

            Open one of your crates to receive a weapon. To check which crates contain which items, check `{prefix}help crates`.
            This command takes up a lot of space, so choose a spammy channel to open crates."""
        )
        if ctx.character_data[f"crates_{rarity}"] < amount:
            return await ctx.send(
                _(
                    "Seems like you don't have {amount} crate(s) of this rarity yet."
                    " Vote me up to get a random one or find them!"
                ).format(amount=amount)
            )

        async with self.bot.pool.acquire() as conn:
            await conn.execute(
                f'UPDATE profile SET "crates_{rarity}"="crates_{rarity}"-$1 WHERE'
                ' "user"=$2;',
                amount,
                ctx.author.id,
            )

            if rarity == "mystery":
                crates = {
                    "common": 0,
                    "uncommon": 0,
                    "rare": 0,
                    "magic": 0,
                    "legendary": 0,
                }

                for _i in range(amount):
                    rng = random.randint(0, 10000)

                    if rng < 20:
                        new_rarity = "legendary"
                    elif rng < 200:
                        new_rarity = "magic"
                    elif rng < 1000:
                        new_rarity = "rare"
                    elif rng < 2000:
                        new_rarity = "uncommon"
                    else:
                        new_rarity = "common"

                    crates[new_rarity] += 1

                await conn.execute(
                    'UPDATE profile SET "crates_common"="crates_common"+$1, "crates_uncommon"="crates_uncommon"+$2, "crates_rare"="crates_rare"+$3, "crates_magic"="crates_magic"+$4, "crates_legendary"="crates_legendary"+$5 WHERE "user"=$6;',
                    crates["common"],
                    crates["uncommon"],
                    crates["rare"],
                    crates["magic"],
                    crates["legendary"],
                    ctx.author.id,
                )

                for r, a in crates.items():
                    if a > 0:
                        await self.bot.log_transaction(
                            ctx,
                            from_=1,
                            to=ctx.author.id,
                            subject="crates",
                            data={"Rarity": r, "Amount": a},
                            conn=conn,
                        )

                text = _(
                    "You opened {mystery_amount} {mystery_emoji} and received:\n"
                    "- {common_amount} {common_emoji}\n"
                    "- {uncommon_amount} {uncommon_emoji}\n"
                    "- {rare_amount} {rare_emoji}\n"
                    "- {magic_amount} {magic_emoji}\n"
                    "- {legendary_amount} {legendary_emoji}"
                ).format(
                    mystery_amount=amount,
                    mystery_emoji=self.emotes.mystery,
                    common_amount=crates["common"],
                    common_emoji=self.emotes.common,
                    uncommon_amount=crates["uncommon"],
                    uncommon_emoji=self.emotes.uncommon,
                    rare_amount=crates["rare"],
                    rare_emoji=self.emotes.rare,
                    magic_amount=crates["magic"],
                    magic_emoji=self.emotes.magic,
                    legendary_amount=crates["legendary"],
                    legendary_emoji=self.emotes.legendary,
                )

                await ctx.send(text)

            else:
                items = []
                for _i in range(amount):
                    # A number to detemine the crate item range
                    rand = random.randint(0, 9)
                    if rarity == "common":
                        if rand < 2:  # 20% 20-30
                            minstat, maxstat = (20, 30)
                        elif rand < 5:  # 30% 10-19
                            minstat, maxstat = (10, 19)
                        else:  # 50% 1-9
                            minstat, maxstat = (1, 9)
                    elif rarity == "uncommon":
                        if rand < 2:  # 20% 30-35
                            minstat, maxstat = (30, 35)
                        elif rand < 5:  # 30% 20-29
                            minstat, maxstat = (20, 29)
                        else:  # 50% 10-19
                            minstat, maxstat = (10, 19)
                    elif rarity == "rare":
                        if rand < 2:  # 20% 35-40
                            minstat, maxstat = (35, 40)
                        elif rand < 5:  # 30% 30-34
                            minstat, maxstat = (30, 34)
                        else:  # 50% 20-29
                            minstat, maxstat = (20, 29)
                    elif rarity == "magic":
                        if rand < 2:  # 20% 41-45
                            minstat, maxstat = (41, 45)
                        elif rand < 5:  # 30% 35-40
                            minstat, maxstat = (35, 40)
                        else:
                            minstat, maxstat = (30, 34)
                    elif rarity == "legendary":  # no else because why
                        if rand < 2:  # 20% 49-50
                            minstat, maxstat = (49, 50)
                        elif rand < 5:  # 30% 46-48
                            minstat, maxstat = (46, 48)
                        else:  # 50% 41-45
                            minstat, maxstat = (41, 45)

                    item = await self.bot.create_random_item(
                        minstat=minstat,
                        maxstat=maxstat,
                        minvalue=1,
                        maxvalue=250,
                        owner=ctx.author,
                        conn=conn,
                    )
                    items.append(item)
                    await self.bot.log_transaction(
                        ctx,
                        from_=1,
                        to=ctx.author.id,
                        subject="item",
                        data={"Name": item["name"], "Value": item["value"]},
                        conn=conn,
                    )

                if amount == 1:
                    embed = discord.Embed(
                        title=_("You gained an item!"),
                        description=_("You found a new item when opening a crate!"),
                        color=0xFF0000,
                    )
                    embed.set_thumbnail(url=ctx.author.display_avatar.url)
                    embed.add_field(name=_("ID"), value=item["id"], inline=False)
                    embed.add_field(name=_("Name"), value=item["name"], inline=False)
                    embed.add_field(name=_("Type"), value=item["type"], inline=False)
                    embed.add_field(name=_("Damage"), value=item["damage"], inline=True)
                    embed.add_field(name=_("Armor"), value=item["armor"], inline=True)
                    embed.add_field(
                        name=_("Value"), value=f"${item['value']}", inline=False
                    )
                    embed.set_footer(
                        text=_("Remaining {rarity} crates: {crates}").format(
                            crates=ctx.character_data[f"crates_{rarity}"] - 1,
                            rarity=rarity,
                        )
                    )
                    await ctx.send(embed=embed)
                    if rarity == "legendary":
                        await self.bot.public_log(
                            f"**{ctx.author}** opened a legendary crate and received"
                            f" {item['name']} with **{item['damage'] or item['armor']}"
                            f" {'damage' if item['damage'] else 'armor'}**."
                        )
                    elif rarity == "magic" and item["damage"] + item["armor"] >= 41:
                        if item["damage"] >= 41:
                            await self.bot.public_log(
                                f"**{ctx.author}** opened a magic crate and received"
                                f" {item['name']} with **{item['damage'] or item['armor']}"
                                f" {'damage' if item['damage'] else 'armor'}**."
                            )
                else:
                    stats_raw = [i["damage"] + i["armor"] for i in items]
                    stats = Counter(stats_raw)
                    types = Counter([i["type"] for i in items])
                    most_common = "\n".join(
                        [f"- {i[0]} (x{i[1]})" for i in stats.most_common(5)]
                    )
                    most_common_types = "\n".join(
                        [f"- {i[0]} (x{i[1]})" for i in types.most_common()]
                    )
                    top = "\n".join([f"- {i}" for i in sorted(stats, reverse=True)[:5]])
                    average_stat = round(sum(stats_raw) / amount, 2)
                    await ctx.send(
                        _(
                            "Successfully opened {amount} {rarity} crates. Average stat:"
                            " {average_stat}\nMost common stats:\n```\n{most_common}\n```\nBest"
                            " stats:\n```\n{top}\n```\nTypes:\n```\n{most_common_types}\n```"
                        ).format(
                            amount=amount,
                            rarity=rarity,
                            average_stat=average_stat,
                            most_common=most_common,
                            top=top,
                            most_common_types=most_common_types,
                        )
                    )
                    if rarity == "legendary":
                        await self.bot.public_log(
                            f"**{ctx.author}** opened {amount} legendary crates and received"
                            f" stats:\n```\n{most_common}\n```\nAverage: {average_stat}"
                        )
                    elif rarity == "magic":
                        await self.bot.public_log(
                            f"**{ctx.author}** opened {amount} magic crates and received"
                            f" stats:\n```\n{most_common}\n```\nAverage: {average_stat}"
                        )

    import random

    @has_char()
    @user_cooldown(43200)
    @commands.command(brief=_("Vote and get crates"))
    @locale_doc
    async def vote(self, ctx):
        _(
            """Vote and get crates.

            Vote and get 2 crates, with each crate having a chance of being common (89%), uncommon (6%), rare (4%), magic (0.9%) or legendary (0.1%).

            This command has a cooldown of 12 hours."""
        )
        rarities = ["common"] * 890 + ["uncommon"] * 60 + ["rare"] * 40 + ["magic"] * 9 + ["legendary"] + ["mystery"] * 50
        rarity1 = random.choice(rarities)
        rarity2 = random.choice(rarities)

        async with self.bot.pool.acquire() as conn:
            await conn.execute(
                f'UPDATE profile SET "crates_{rarity1}"="crates_{rarity1}"+1 WHERE'
                ' "user"=$1;',
                ctx.author.id,
            )
            await conn.execute(
                f'UPDATE profile SET "crates_{rarity2}"="crates_{rarity2}"+1 WHERE'
                ' "user"=$1;',
                ctx.author.id,
            )
            await self.bot.log_transaction(
                ctx,
                from_=1,
                to=ctx.author.id,
                subject="crates",
                data={"Rarity": rarity1, "Amount": 1},
                conn=conn,
            )
            await self.bot.log_transaction(
                ctx,
                from_=1,
                to=ctx.author.id,
                subject="crates",
                data={"Rarity": rarity2, "Amount": 1},
                conn=conn,
            )

        emotes = {
            "common": "<:F_common:1139514874016309260>",
            "uncommon": "<:F_uncommon:1139514875828252702>",
            "rare": "<:F_rare:1139514880517484666>",
            "magic": "<:F_Magic:1139514865174720532>",
            "legendary": "<:F_Legendary:1139514868400132116>",
            "mystery": "<:F_mystspark:1139521536320094358>"
        }

        if rarity1 == rarity2:
            await ctx.send(
                _("Yeah.. there is no voting, but hey and got 2 {emote} {rarity} crates for your efforts!").format(
                    emote=emotes[rarity1], rarity=rarity1
                )
            )
        else:
            await ctx.send(
                _("Yeah.. there is no voting, but hey and got a {emote1} {rarity1} crate and a {emote2} {rarity2} "
                  "crate for your efforts!").format(
                    emote1=emotes[rarity1], rarity1=rarity1, emote2=emotes[rarity2], rarity2=rarity2
                )
            )

    @has_char()
    @commands.command(aliases=["tc"], brief=_("Give crates to someone"))
    @locale_doc
    async def tradecrate(
            self,
            ctx,
            other: MemberWithCharacter,
            amount: IntGreaterThan(0) = 1,
            rarity: CrateRarity = "common",
    ):
        _(
            """`<other>` - A user with a character
            `[amount]` - A whole number greater than 0; defaults to 1
            `[rarity]` - The crate's rarity to trade, can be common, uncommon, rare, magic or legendary; defaults to common

            Give your crates to another person.

            Players must combine this command with `{prefix}give` for a complete trade."""
        )
        if other == ctx.author:
            return await ctx.send(_("Very funny..."))
        elif other == ctx.me:
            return await ctx.send(
                _("For me? I'm flattered, but I can't accept this...")
            )
        if ctx.character_data[f"crates_{rarity}"] < amount:
            return await ctx.send(_("You don't have any crates of this rarity."))
        async with self.bot.pool.acquire() as conn:
            await conn.execute(
                f'UPDATE profile SET "crates_{rarity}"="crates_{rarity}"-$1 WHERE'
                ' "user"=$2;',
                amount,
                ctx.author.id,
            )
            await conn.execute(
                f'UPDATE profile SET "crates_{rarity}"="crates_{rarity}"+$1 WHERE'
                ' "user"=$2;',
                amount,
                other.id,
            )
            await self.bot.log_transaction(
                ctx,
                from_=ctx.author.id,
                to=other.id,
                subject="crates",
                data={"Rarity": rarity, "Amount": amount},
                conn=conn,
            )

        await ctx.send(
            _("Successfully gave {amount} {rarity} crate(s) to {other}.").format(
                amount=amount, other=other.mention, rarity=rarity
            )
        )

    @has_char()
    @user_cooldown(180)
    @commands.command(
        aliases=["offercrates", "oc"], brief=_("Offer crates to another player")
    )
    @locale_doc
    async def offercrate(
            self,
            ctx,
            quantity: IntGreaterThan(0),
            rarity: CrateRarity,
            price: IntFromTo(0, 100_000_000),
            buyer: MemberWithCharacter,
    ):
        _(
            """`<quantity>` - The quantity of crates to offer
            `<rarity>` - The rarity of crate to offer. First letter of the rarity is also accepted.
            `<price>` - The price to be paid by the buyer, can be a number from 0 to 100000000
            `<buyer>` - Another IdleRPG player to offer the crates to

            Offer crates to another player. Once the other player accepts, they will receive the crates and you will receive their payment.
            Example:
            `{prefix}offercrate 5 common 75000 @buyer#1234`
            `{prefix}oc 5 c 75000 @buyer#1234`"""
        )
        if buyer == ctx.author:
            await ctx.send(_("You may not offer crates to yourself."))
            return await self.bot.reset_cooldown(ctx)
        elif buyer == ctx.me:
            await ctx.send(_("No, I don't want any crates."))
            return await self.bot.reset_cooldown(ctx)

        if ctx.character_data[f"crates_{rarity}"] < quantity:
            await ctx.send(
                _(
                    "You don't have {quantity} {rarity} crate(s). Check"
                    " `{prefix}crates`."
                ).format(quantity=quantity, rarity=rarity, prefix=ctx.clean_prefix)
            )
            return await self.bot.reset_cooldown(ctx)

        if not await ctx.confirm(
                _(
                    "{author}, are you sure you want to offer **{quantity} {emoji}"
                    " {rarity}** crate(s) for **${price:,.0f}**?"
                ).format(
                    author=ctx.author.mention,
                    quantity=quantity,
                    emoji=getattr(self.emotes, rarity),
                    rarity=rarity,
                    price=price,
                )
        ):
            await ctx.send(_("Offer cancelled."))
            return await self.bot.reset_cooldown(ctx)

        try:
            if not await ctx.confirm(
                    _(
                        "{buyer}, {author} offered you **{quantity} {emoji} {rarity}**"
                        " crate(s) for **${price:,.0f}!** React to buy it! You have **2"
                        " Minutes** to accept the trade or the offer will be cancelled."
                    ).format(
                        buyer=buyer.mention,
                        author=ctx.author.mention,
                        quantity=quantity,
                        emoji=getattr(self.emotes, rarity),
                        rarity=rarity,
                        price=price,
                    ),
                    user=buyer,
                    timeout=120,
            ):
                await ctx.send(
                    _("They didn't want to buy the crate(s). Offer cancelled.")
                )
                return await self.bot.reset_cooldown(ctx)
        except self.bot.paginator.NoChoice:
            await ctx.send(_("They couldn't make up their mind. Offer cancelled."))
            return await self.bot.reset_cooldown(ctx)

        async with self.bot.pool.acquire() as conn:
            if not await has_money(self.bot, buyer.id, price, conn=conn):
                await ctx.send(
                    _("{buyer}, you're too poor to buy the crate(s)!").format(
                        buyer=buyer.mention
                    )
                )
                return await self.bot.reset_cooldown(ctx)
            crates = await conn.fetchval(
                f'SELECT crates_{rarity} FROM profile WHERE "user"=$1;', ctx.author.id
            )
            if crates < quantity:
                return await ctx.send(
                    _(
                        "The seller traded/opened the crate(s) in the meantime. Offer"
                        " cancelled."
                    )
                )
            await conn.execute(
                f'UPDATE profile SET "crates_{rarity}"="crates_{rarity}"-$1,'
                ' "money"="money"+$2 WHERE "user"=$3;',
                quantity,
                price,
                ctx.author.id,
            )
            await conn.execute(
                f'UPDATE profile SET "crates_{rarity}"="crates_{rarity}"+$1,'
                ' "money"="money"-$2 WHERE "user"=$3;',
                quantity,
                price,
                buyer.id,
            )
            await self.bot.log_transaction(
                ctx,
                from_=ctx.author.id,
                to=buyer.id,
                subject="crates",
                data={
                    "Quantity": quantity,
                    "Rarity": rarity,
                    "Price": price,
                },
                conn=conn,
            )
            await self.bot.log_transaction(
                ctx,
                from_=buyer.id,
                to=ctx.author.id,
                subject="money",
                data={
                    "Price": price,
                    "Quantity": quantity,
                    "Rarity": rarity,
                },
                conn=conn,
            )

        await ctx.send(
            _(
                "{buyer}, you've successfully bought **{quantity} {emoji} {rarity}**"
                " crate(s) from {seller}. Use `{prefix}crates` to view your updated"
                " crates."
            ).format(
                buyer=buyer.mention,
                quantity=quantity,
                emoji=getattr(self.emotes, rarity),
                rarity=rarity,
                seller=ctx.author.mention,
                prefix=ctx.clean_prefix,
            )
        )


async def setup(bot):
    await bot.add_cog(Crates(bot))
