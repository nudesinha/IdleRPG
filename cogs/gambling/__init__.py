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
import os

from contextlib import suppress
from enum import Enum
from functools import partial

import discord

from discord.enums import ButtonStyle
from discord.ext import commands
from discord.interactions import Interaction
from discord.ui.button import Button, button

from classes.bot import Bot
from classes.context import Context
from classes.converters import CoinSide, IntFromTo, IntGreaterThan, MemberWithCharacter
from utils import random
from utils.checks import has_char, has_money, user_has_char
from utils.i18n import _, locale_doc
from utils.roulette import RouletteGame


class BlackJackAction(Enum):
    Hit = 0
    Stand = 1
    DoubleDown = 2
    ChangeDeck = 3
    Split = 4


class InsuranceView(discord.ui.View):
    def __init__(
            self, user: discord.User, future: asyncio.Future[bool], *args, **kwargs
    ):
        super().__init__(*args, **kwargs)
        self.user = user
        self.future = future

    async def interaction_check(self, interaction: Interaction) -> bool:
        return interaction.user.id == self.user.id

    @button(label="Take insurance", style=ButtonStyle.green, emoji="\U0001f4b8")
    async def insurance(self, interaction: Interaction, button: Button) -> None:
        self.stop()
        self.future.set_result(True)
        await interaction.response.defer()

    @button(label="Don't take insurance", style=ButtonStyle.red, emoji="\U000026a0")
    async def no_insurance(self, interaction: Interaction, button: Button) -> None:
        self.stop()
        self.future.set_result(False)
        await interaction.response.defer()

    async def on_timeout(self) -> None:
        self.future.set_result(False)


class BlackJackView(discord.ui.View):
    def __init__(
            self,
            user: discord.User,
            future: asyncio.Future[BlackJackAction],
            *args,
            **kwargs,
    ) -> None:
        self.user = user
        self.future = future

        # Buttons to show
        self.hit = kwargs.pop("hit", False)
        self.stand = kwargs.pop("stand", False)
        self.double_down = kwargs.pop("double_down", False)
        self.change_deck = kwargs.pop("change_deck", False)
        self.split = kwargs.pop("split", False)

        super().__init__(*args, **kwargs)

        # Row 1 is primary actions
        hit = Button(
            style=ButtonStyle.primary,
            label="Hit",
            disabled=not self.hit,
            emoji="\U00002934",
            row=0,
        )
        stand = Button(
            style=ButtonStyle.primary,
            label="Stand",
            disabled=not self.stand,
            emoji="\U00002935",
            row=0,
        )
        double_down = Button(
            style=ButtonStyle.primary,
            label="Double Down",
            disabled=not self.double_down,
            emoji="\U000023ec",
            row=0,
        )

        # Row 2 is the two split actions
        change_deck = Button(
            style=ButtonStyle.secondary,
            label="Change Deck",
            disabled=not self.change_deck,
            emoji="\U0001F501",
            row=1,
        )
        split = Button(
            style=ButtonStyle.secondary,
            label="Split",
            disabled=not self.split,
            emoji="\U00002194",
            row=1,
        )

        hit.callback = partial(self.handle, action=BlackJackAction.Hit)
        stand.callback = partial(self.handle, action=BlackJackAction.Stand)
        double_down.callback = partial(self.handle, action=BlackJackAction.DoubleDown)
        change_deck.callback = partial(self.handle, action=BlackJackAction.ChangeDeck)
        split.callback = partial(self.handle, action=BlackJackAction.Split)

        self.add_item(hit)
        self.add_item(stand)
        self.add_item(double_down)
        self.add_item(change_deck)
        self.add_item(split)

    async def interaction_check(self, interaction: Interaction) -> bool:
        return interaction.user.id == self.user.id

    async def handle(self, interaction: Interaction, action: BlackJackAction) -> None:
        self.stop()
        self.future.set_result(action)
        await interaction.response.defer()

    async def on_timeout(self) -> None:
        self.future.set_exception(asyncio.TimeoutError())


class BlackJack:
    def __init__(self, ctx: Context, money: int) -> None:
        self.cards = {
            "adiamonds": "<:ace_of_diamonds:1145400362552012800>",
            "2diamonds": "<:2_of_diamonds:1145400865209987223>",
            "3diamonds": "<:3_of_diamonds:1145400877679648858>",
            "4diamonds": "<:4_of_diamonds:1145400270830960660>",
            "5diamonds": "<:5_of_diamonds:1145400282239479848>",
            "6diamonds": "<:6_of_diamonds:1145400297791950909>",
            "7diamonds": "<:7_of_diamonds:1145400309921886358>",
            "8diamonds": "<:8_of_diamonds:1145400320457973971>",
            "9diamonds": "<:9_of_diamonds:1145400335716864082>",
            "10diamonds": "<:10_of_diamonds:1145400349071523981>",
            "jdiamonds": "<:jack_of_diamonds2:1145400380558151722>",
            "qdiamonds": "<:queen_of_diamonds2:1145400426175398009>",
            "kdiamonds": "<:king_of_diamonds2:1145400404075626536>",
            "aclubs": "<:ace_of_clubs:1145400358768758785>",
            "2clubs": "<:2_of_clubs:1145400863129604127>",
            "3clubs": "<:3_of_clubs:1145400874311614515>",
            "4clubs": "<:4_of_clubs:1145400280343662623>",
            "5clubs": "<:5_of_clubs:1145400280343662623>",
            "6clubs": "<:6_of_clubs:1145400295971631184>",
            "7clubs": "<:7_of_clubs:1145400306738409563>",
            "8clubs": "<:8_of_clubs:1145400318503436318>",
            "9clubs": "<:9_of_clubs:1145400334139793418>",
            "10clubs": "<:10_of_clubs:1145400346668171276>",
            "jclubs": "<:jack_of_clubs2:1145400373381709966>",
            "qclubs": "<:queen_of_clubs2:1145400422094352530>",
            "kclubs": "<:king_of_clubs2:1145400399654834208>",
            "ahearts": "<:ace_of_hearts:1145400364535926824>",
            "2hearts": "<:2_of_hearts:1145400868477354005>",
            "3hearts": "<:3_of_hearts:1145400882490507304>",
            "4hearts": "<:4_of_hearts:1145400273448214619>",
            "5hearts": "<:5_of_hearts:1145400286001766521>",
            "6hearts": "<:6_of_hearts:1145400301222887444>",
            "7hearts": "<:7_of_hearts:1145400312534929419>",
            "8hearts": "<:8_of_hearts:1145400324744548562>",
            "9hearts": "<:9_of_hearts:1145400339537862749>",
            "10hearts": "<:10_of_hearts:1145400352871559268>",
            "jhearts": "<:jack_of_hearts2:1145400387071909888>",
            "qhearts": "<:queen_of_hearts2:1145400432018063381>",
            "khearts": "<:king_of_hearts2:1145400409742118934>",
            "aspades": "<:ace_of_spades:1145400368105279658>",
            "2spades": "<:2_of_spades:1145400872340299796>",
            "3spades": "<:3_of_spades:1145400874311614515>",
            "4spades": "<:4_of_spades:1145400276686225408>",
            "5spades": "<:5_of_spades:1145400290531622943>",
            "6spades": "<:6_of_spades:1145400304888721548>",
            "7spades": "<:7_of_spades:1145400314955055165>",
            "8spades": "<:8_of_spades:1145400329354105013>",
            "9spades": "<:9_of_spades:1145400342763282546>",
            "10spades": "<:10_of_spades:1145400356424130712>",
            "jspades": "<:jack_of_spades2:1145400391798894612>",
            "qspades": "<:queen_of_spades2:1145400436891865089>",
            "kspades": "<:king_of_spades2:1145400416608194680>",

        }
        self.deck: list[tuple[int, str, str]] = []
        self.prepare_deck()
        self.expected_player_money = ctx.character_data["money"] - money
        self.money_spent = money
        self.payout = money
        self.ctx = ctx
        self.msg = None
        self.over = False
        self.insurance = False
        self.doubled = False
        self.twodecks = False

    def prepare_deck(self) -> None:
        for colour in ["hearts", "diamonds", "spades", "clubs"]:
            for value in range(2, 15):  # 11 = Jack, 12 = Queen, 13 = King, 14 = Ace
                if value == 11:
                    card = "j"
                elif value == 12:
                    card = "q"
                elif value == 13:
                    card = "k"
                elif value == 14:
                    card = "a"
                else:
                    card = str(value)
                self.deck.append((value, colour, self.cards[f"{card}{colour}"]))
        self.deck = self.deck * 6  # BlackJack is played with 6 sets of cards
        self.deck = random.shuffle(self.deck)

    def deal(self) -> tuple[int, str, str]:
        return self.deck.pop()

    def total(self, hand: list[tuple[int, str, str]]) -> int:
        value = sum(
            card[0] if card[0] < 11 else 10 for card in hand if card[0] != 14
        )  # ignore aces for now
        aces = sum(1 for card in hand if card[0] == 14)
        # Assume the minimum of 1 for every ace
        value += aces
        # Now, add 10 for every ace as long as it's below 21
        for i in range(aces):
            if value + 10 <= 21:
                value += 10
            else:
                break

        return value

    def has_bj(self, hand: list[tuple[int, str, str]]) -> bool:
        return self.total(hand) == 21

    def samevalue(self, a: int, b: int) -> bool:
        if a == b:
            return True
        if a in [10, 11, 12, 13] and b in [10, 11, 12, 13]:
            return True
        return False

    def splittable(self, hand) -> bool:
        if self.samevalue(hand[0][0], hand[1][0]) and not self.twodecks:
            return True
        return False

    def hit(self, hand: list[tuple[int, str, str]]) -> list[tuple[int, str, str]]:
        card = self.deal()
        hand.append(card)
        return hand

    def split(
            self, hand
    ) -> tuple[list[tuple[int, str, str]], list[tuple[int, str, str]]]:
        hand1 = hand[:-1]
        hand2 = [hand[-1]]
        return (hand1, hand2)

    async def player_takes_insurance(self) -> bool:
        if self.payout > 0:
            insurance_cost = self.payout // 2
            self.expected_player_money -= insurance_cost
            self.money_spent += insurance_cost

            async with self.ctx.bot.pool.acquire() as conn:
                if not await has_money(
                        self.ctx.bot, self.ctx.author.id, insurance_cost, conn=conn
                ):
                    return False

                await conn.execute(
                    'UPDATE profile SET "money"="money"-$1 WHERE "user"=$2;',
                    insurance_cost,
                    self.ctx.author.id,
                )

                await self.ctx.bot.log_transaction(
                    self.ctx,
                    from_=1,
                    to=self.ctx.author.id,
                    subject="gambling",
                    data={"Amount": insurance_cost},
                    conn=conn,
                )

        return True

    async def player_win(self) -> None:
        if self.payout > 0:
            async with self.ctx.bot.pool.acquire() as conn:
                await conn.execute(
                    'UPDATE profile SET "money"="money"+$1 WHERE "user"=$2;',
                    self.payout * 2,
                    self.ctx.author.id,
                )

                await self.ctx.bot.log_transaction(
                    self.ctx,
                    from_=1,
                    to=self.ctx.author.id,
                    subject="gambling",
                    data={"Amount": self.payout * 2},
                    conn=conn,
                )

    async def player_bj_win(self) -> None:
        if self.payout > 0:
            total = int(self.payout * 2.5)

            async with self.ctx.bot.pool.acquire() as conn:
                await conn.execute(
                    'UPDATE profile SET "money"="money"+$1 WHERE "user"=$2;',
                    total,
                    self.ctx.author.id,
                )

                await self.ctx.bot.log_transaction(
                    self.ctx,
                    from_=1,
                    to=self.ctx.author.id,
                    subject="gambling",
                    data={"Amount": total},
                    conn=conn,
                )

    async def player_cashback(self, with_insurance: bool = False) -> None:
        if self.payout > 0:
            amount = self.money_spent if with_insurance else self.payout

            async with self.ctx.bot.pool.acquire() as conn:
                await conn.execute(
                    'UPDATE profile SET "money"="money"+$1 WHERE "user"=$2;',
                    amount,
                    self.ctx.author.id,
                )

                await self.ctx.bot.log_transaction(
                    self.ctx,
                    from_=1,
                    to=self.ctx.author.id,
                    subject="gambling",
                    data={"Amount": amount},
                    conn=conn,
                )

    def pretty(self, hand: list[tuple[int, str, str]]) -> str:
        return " ".join([card[2] for card in hand])

    async def send_insurance(
            self,
    ) -> bool:
        player = self.total(self.player)
        dealer = self.total(self.dealer)

        text = _(
            "The dealer has a {pretty_dealer} for a total of {dealer}\nYou have a"
            " {pretty_player} for a total of {player}"
        ).format(
            pretty_dealer=self.pretty(self.dealer),
            dealer=dealer,
            pretty_player=self.pretty(self.player),
            player=player,
        )

        future = asyncio.Future()
        view = InsuranceView(self.ctx.author, future, timeout=20.0)

        if not self.msg:
            self.msg = await self.ctx.send(text, view=view)
        else:
            await self.msg.edit(content=text, view=view)

        return await future

    async def send(
            self,
            additional: str = "",
            hit: bool = False,
            stand: bool = False,
            double_down: bool = False,
            change_deck: bool = False,
            split: bool = False,
            wait_for_action: bool = True,
    ) -> BlackJackAction | None:
        player = self.total(self.player)
        dealer = self.total(self.dealer)

        text = _(
            "The dealer has a {pretty_dealer} for a total of {dealer}\nYou have a"
            " {pretty_player} for a total of {player}\n{additional}"
        ).format(
            pretty_dealer=self.pretty(self.dealer),
            dealer=dealer,
            pretty_player=self.pretty(self.player),
            player=player,
            additional=additional,
        )

        if wait_for_action:
            future = asyncio.Future()
            view = BlackJackView(
                self.ctx.author,
                future,
                hit=hit,
                stand=stand,
                double_down=double_down,
                change_deck=change_deck,
                split=split,
                timeout=20.0,
            )
        else:
            view = None

        if not self.msg:
            self.msg = await self.ctx.send(text, view=view)
        else:
            await self.msg.edit(content=text, view=view)

        if wait_for_action:
            return await future

    async def run(self):
        self.player = [self.deal()]
        self.player2 = None
        self.dealer = [self.deal()]
        # Prompt for insurance
        if self.dealer[0][0] > 9 and self.expected_player_money >= self.payout // 2:
            self.insurance = await self.send_insurance()

            if self.insurance:
                if not await self.player_takes_insurance():
                    return await self.send(
                        additional=_(
                            "You do not have the money to afford insurance anymore."
                        ),
                        wait_for_action=False,
                    )

        self.player = self.hit(self.player)
        self.dealer = self.hit(self.dealer)

        if self.has_bj(self.dealer):
            if self.insurance:
                await self.player_cashback(with_insurance=True)
                return await self.send(
                    additional=_(
                        "The dealer got a blackjack. You had insurance and lost"
                        " nothing."
                    ),
                    wait_for_action=False,
                )
            else:
                return await self.send(
                    additional=_(
                        "The dealer got a blackjack. You lost **${money}**."
                    ).format(money=self.money_spent),
                    wait_for_action=False,
                )
        elif self.has_bj(self.player):
            await self.player_bj_win()
            return await self.send(
                additional=_("You got a blackjack and won **${money}**!").format(
                    money=int(self.payout * 2.5) - self.money_spent
                ),
                wait_for_action=False,
            )

        possible_actions = {
            "hit": True,
            "stand": True,
            "double_down": self.expected_player_money - self.payout >= 0,
            "change_deck": False,
            "split": False,
        }
        additional = ""

        while (
                self.total(self.dealer) < 22
                and self.total(self.player) < 22
                and not self.over
        ):
            possible_actions["change_deck"] = self.twodecks and not self.doubled
            possible_actions["split"] = self.splittable(self.player)

            # Prompt for an action
            try:
                action = await self.send(additional=additional, **possible_actions)
            except asyncio.TimeoutError:
                await self.ctx.bot.reset_cooldown(self.ctx)
                return await self.ctx.send(
                    _("Blackjack timed out... You lost your money!")
                )

            while self.total(self.dealer) < 17:
                self.dealer = self.hit(self.dealer)

            if action == BlackJackAction.Hit:
                if self.doubled:
                    possible_actions["hit"] = False
                    possible_actions["stand"] = True
                self.player = self.hit(self.player)

            elif action == BlackJackAction.Stand:
                self.over = True

            elif action == BlackJackAction.Split:
                self.player2, self.player = self.split(self.player)
                self.hit(self.player)
                self.hit(self.player2)
                self.twodecks = True
                possible_actions["split"] = False
                additional = _("Split current hand and switched to the second side.")

            elif action == BlackJackAction.ChangeDeck:
                self.player, self.player2 = self.player2, self.player
                additional = _("Switched to the other side.")

            elif action == BlackJackAction.DoubleDown:
                self.doubled = True
                if self.payout > 0:
                    self.expected_player_money -= self.payout
                    self.money_spent += self.payout

                    async with self.ctx.bot.pool.acquire() as conn:
                        if not await has_money(
                                self.ctx.bot, self.ctx.author.id, self.payout, conn=conn
                        ):
                            return await self.ctx.send(
                                _("Invalid. You're too poor and lose the match.")
                            )

                        await conn.execute(
                            'UPDATE profile SET "money"="money"-$1 WHERE "user"=$2;',
                            self.payout,
                            self.ctx.author.id,
                        )
                        await self.ctx.bot.log_transaction(
                            self.ctx,
                            from_=self.ctx.author.id,
                            to=2,
                            subject="gambling",
                            data={"Amount": self.payout},
                            conn=conn,
                        )

                self.payout *= 2
                possible_actions["double_down"] = False
                possible_actions["stand"] = False
                if self.twodecks:
                    possible_actions["change_deck"] = False
                additional = _(
                    "You doubled your bid in exchange for only receiving one more"
                    " card."
                )

        player = self.total(self.player)
        dealer = self.total(self.dealer)

        if player > 21:
            await self.send(
                additional=_("You busted and lost **${money}**.").format(
                    money=self.money_spent
                ),
                wait_for_action=False,
            )
        elif dealer > 21:
            await self.send(
                additional=_("Dealer busts and you won **${money}**!").format(
                    money=self.payout * 2 - self.money_spent
                ),
                wait_for_action=False,
            )
            await self.player_win()
        else:
            if player > dealer:
                await self.send(
                    additional=_(
                        "You have a higher score than the dealer and have won"
                        " **${money}**"
                    ).format(money=self.payout * 2 - self.money_spent),
                    wait_for_action=False,
                )
                await self.player_win()
            elif dealer > player:
                await self.send(
                    additional=_(
                        "Dealer has a higher score than you and wins. You lost"
                        " **${money}**."
                    ).format(money=self.money_spent),
                    wait_for_action=False,
                )
            else:
                await self.player_cashback()
                await self.send(
                    additional=_("It's a tie, you got your **${money}** back.").format(
                        money=self.payout
                    ),
                    wait_for_action=False,
                )


class Gambling(commands.Cog):
    def __init__(self, bot: Bot) -> None:
        self.bot = bot
        self.cards = os.listdir("assets/cards")

    @has_char()
    @commands.cooldown(1, 15, commands.BucketType.user)
    @commands.command(aliases=["card"], brief=_("Draw a card."))
    @locale_doc
    async def draw(
            self, ctx, enemy: MemberWithCharacter = None, money: IntGreaterThan(-1) = 0
    ):
        _(
            """`[enemy]` - A user who has a profile; defaults to None
            `[money]` - The bet money. A whole number that can be 0 or greater; defaults to 0

            Draws a random card from the 52 French playing cards. Playing Draw with someone for money is also available if the enemy is mentioned. The player with higher value of the drawn cards will win the bet money.

            This command has no effect on your balance if done with no enemy mentioned.
            (This command has a cooldown of 15 seconds.)"""
        )
        if not enemy:
            return await ctx.send(
                content=f"{ctx.author.mention} you drew:",
                file=discord.File(f"assets/cards/{random.choice(self.cards)}"),
            )
        else:
            if enemy == ctx.author:
                return await ctx.send(_("Please choose someone else."))
            if enemy == ctx.me:
                return await ctx.send(_("You should choose a human to play with you."))

            if ctx.character_data["money"] < money:
                return await ctx.send(_("You are too poor."))

            await self.bot.pool.execute(
                'UPDATE profile SET "money"="money"-$1 WHERE "user"=$2;',
                money,
                ctx.author.id,
            )

            async def money_back():
                await self.bot.pool.execute(
                    'UPDATE profile SET "money"="money"+$1 WHERE "user"=$2;',
                    money,
                    ctx.author.id,
                )
                return await self.bot.reset_cooldown(ctx)

            try:
                if not await ctx.confirm(
                        _(
                            "{author} challenges {enemy} to a game of Draw for"
                            " **${money}**. Do you accept?"
                        ).format(
                            author=ctx.author.mention,
                            enemy=enemy.mention,
                            money=money,
                        ),
                        user=enemy,
                        timeout=15,
                ):
                    await money_back()
                    return await ctx.send(
                        _(
                            "They declined. They don't want to play a game of Draw with"
                            " you {author}."
                        ).format(author=ctx.author.mention)
                    )
            except self.bot.paginator.NoChoice:
                await money_back()
                return await ctx.send(
                    _(
                        "They didn't choose anything. It seems they're not interested"
                        " to play a game of Draw with you {author}."
                    ).format(author=ctx.author.mention)
                )

            if not await has_money(self.bot, enemy.id, money):
                await money_back()
                return await ctx.send(
                    _("{enemy} You don't have enough money to play.").format(
                        enemy=enemy.mention
                    )
                )

            await self.bot.pool.execute(
                'UPDATE profile SET "money"="money"-$1 WHERE "user"=$2;',
                money,
                enemy.id,
            )

            cards = self.cards.copy()
            cards = random.shuffle(cards)
            rank_values = {
                "jack": 11,
                "queen": 12,
                "king": 13,
                "ace": 14,
            }

            while True:
                try:
                    author_card = cards.pop()
                    enemy_card = cards.pop()
                except IndexError:
                    return await ctx.send(
                        _(
                            "Cards ran out. This is a very rare issue that could mean"
                            " image files for cards have become insufficient. Please"
                            " report this issue to the bot developers."
                        )
                    )

                rank1 = author_card[: author_card.find("_")]
                rank2 = enemy_card[: enemy_card.find("_")]
                drawn_values = [
                    int(rank_values.get(rank1, rank1)),
                    int(rank_values.get(rank2, rank2)),
                ]

                async with self.bot.pool.acquire() as conn:
                    if drawn_values[0] == drawn_values[1]:
                        await conn.execute(
                            'UPDATE profile SET "money"="money"+$1 WHERE "user"=$2 OR'
                            ' "user"=$3;',
                            money,
                            ctx.author.id,
                            enemy.id,
                        )
                        text = _("Nobody won. {author} and {enemy} tied.").format(
                            author=ctx.author.mention,
                            enemy=enemy.mention,
                        )
                    else:
                        players = [ctx.author, enemy]
                        winner = players[drawn_values.index(max(drawn_values))]
                        loser = players[players.index(winner) - 1]
                        await conn.execute(
                            'UPDATE profile SET "money"="money"+$1 WHERE "user"=$2;',
                            money * 2,
                            winner.id,
                        )
                        await self.bot.log_transaction(
                            ctx,
                            from_=loser.id,
                            to=winner.id,
                            subject="gambling",
                            data={"Amount": money},
                            conn=conn,
                        )
                        text = _(
                            "{winner} won the Draw vs {loser}! Congratulations!"
                        ).format(winner=winner.mention, loser=loser.mention)

                await ctx.send(
                    content=(
                        _("{author}, while playing against {enemy}, you drew:").format(
                            author=ctx.author.mention, enemy=enemy.mention
                        )
                    ),
                    file=discord.File(f"assets/cards/{author_card}"),
                )
                await ctx.send(
                    content=(
                        _("{enemy}, while playing against {author}, you drew:").format(
                            enemy=enemy.mention, author=ctx.author.mention
                        )
                    ),
                    file=discord.File(f"assets/cards/{enemy_card}"),
                )
                await ctx.send(text)

                if drawn_values[0] != drawn_values[1]:
                    break
                else:
                    msg = await ctx.send(
                        content=f"{ctx.author.mention}, {enemy.mention}",
                        embed=discord.Embed(
                            title=_("Break the tie?"),
                            description=_(
                                "{author}, {enemy} You tied. Do you want to break the"
                                " tie by playing again for **${money}**?"
                            ).format(
                                author=ctx.author.mention,
                                enemy=enemy.mention,
                                money=money,
                            ),
                            colour=discord.Colour.blurple(),
                        ),
                    )

                    emoji_no = "\U0000274e"
                    emoji_yes = "\U00002705"
                    emojis = (emoji_no, emoji_yes)

                    for emoji in emojis:
                        await msg.add_reaction(emoji)

                    def check(r, u):
                        return (
                                str(r.emoji) in emojis
                                and r.message.id == msg.id
                                and u in [ctx.author, enemy]
                                and not u.bot
                        )

                    async def cleanup() -> None:
                        with suppress(discord.HTTPException):
                            await msg.delete()

                    accept_redraws = {}

                    while len(accept_redraws) < 2:
                        try:
                            reaction, user = await self.bot.wait_for(
                                "reaction_add", timeout=15, check=check
                            )
                        except asyncio.TimeoutError:
                            await cleanup()
                            return await ctx.send(
                                _("One of you or both didn't react on time.")
                            )
                        else:
                            if not (accept := bool(emojis.index(str(reaction.emoji)))):
                                await cleanup()
                                return await ctx.send(
                                    _("{user} declined to break the tie.").format(
                                        user=user.mention
                                    )
                                )
                            if user.id not in accept_redraws:
                                accept_redraws[user.id] = accept

                    await cleanup()

                    if not await has_money(self.bot, ctx.author.id, money):
                        return await ctx.send(
                            _("{author} You don't have enough money to play.").format(
                                author=ctx.author.mention
                            )
                        )
                    if not await has_money(self.bot, enemy.id, money):
                        return await ctx.send(
                            _("{enemy} You don't have enough money to play.").format(
                                enemy=enemy.mention
                            )
                        )

                    await self.bot.pool.execute(
                        'UPDATE profile SET "money"="money"-$1 WHERE "user"=$2 OR'
                        ' "user"=$3;',
                        money,
                        ctx.author.id,
                        enemy.id,
                    )

    @has_char()
    @commands.cooldown(1, 15, commands.BucketType.user)
    @commands.group(
        aliases=["rou"],
        invoke_without_command=True,
        brief=_("Play a game of French Roulette"),
    )
    @locale_doc
    async def roulette(self, ctx, money: IntFromTo(0, 100), *, bid: str):
        _(
            """`<money>` - A whole number from 0 to 100
`<bid>` - What to bid on, see below for details

Play a game of French Roulette.

Possible simple bets:
    - noir    (all black numbers) (1:1 payout)
    - rouge   (all red numbers) (1:1 payout)
    - pair    (all even numbers) (1:1 payout)
    - impair  (all odd numbers) (1:1 payout)
    - manque  (1-18) (1:1 payout)
    - passe   (19-36) (1:1 payout)
    - premier (1-12) (2:1 payout)
    - milieu  (13-24) (2:1 payout)
    - dernier (25-36) (2:1 payout)

Complicated bets:
    - colonne (34/35/36) (all numbers in a row on the betting table, either 1, 4, ..., 34 or 2, 5, ..., 35 or 3, 6, ... 36) (2:1 payout)
    - transversale (vertical low)-(vertical high)    This includes simple and pleine (a vertical row on the betting table, e.g. 19-21. can also be two rows, e.g. 4-9) (11:1 payout for pleine, 5:1 for simple)
        - les trois premiers (numbers 0, 1, 2) (11:1 payout)
    - carre (low)-(high) (a section of four numbers in a square on the betting table, e.g. 23-27) (8:1 payout)
        - les quatre premiers (numbers 0, 1, 2, 3) (8:1 payout)
    - cheval (number 1) (number 2) (a simple bet on two numbers) (17:1 payout)
    - plein (number) (a simple bet on one number) (35:1 payout)

To visualize the rows and columns, use the command: roulette table

This command is in an alpha-stage, which means bugs are likely to happen. Play at your own risk.
(This command has a cooldown of 15 seconds.)"""
        )
        if ctx.character_data["money"] < money:
            return await ctx.send(_("You're too poor."))
        try:
            game = RouletteGame(money, bid)
        except Exception:
            return await ctx.send(
                _(
                    "Your bid input was invalid. Try the help on this command to view"
                    " examples."
                )
            )
        await game.run(ctx)

    @roulette.command(brief=_("Show the roulette table"))
    @locale_doc
    async def table(self, ctx):
        _("""Sends a picture of a French Roulette table.""")
        await ctx.send(file=discord.File("assets/other/roulette.webp"))

    @has_char()
    @commands.cooldown(1, 5, commands.BucketType.user)
    @commands.command(aliases=["coin"], brief=_("Toss a coin"))
    @locale_doc
    async def flip(
            self,
            ctx,
            side: CoinSide | None = "heads",
            *,
            amount: IntFromTo(0, 100_000) = 0,
    ):
        _(
            """`[side]` - The coin side to bet on, can be heads or tails; defaults to heads
            `[amount]` - A whole number from 1 to 100,000; defaults to 0

            Bet money on a coinflip.

            If the coin lands on the side you bet on, you will receive the amount in cash. If it's the other side, you lose that amount.
            (This command has a cooldown of 5 seconds.)"""
        )
        if ctx.character_data["money"] < amount:
            return await ctx.send(_("You are too poor."))
        result = random.choice(
            [
                ("heads", "<:heads:988811246423904296>"),
                ("tails", "<:tails:988811244762980413>"),
            ]
        )
        if result[0] == side:
            if amount > 0:
                async with self.bot.pool.acquire() as conn:
                    await conn.execute(
                        'UPDATE profile SET "money"="money"+$1 WHERE "user"=$2;',
                        amount,
                        ctx.author.id,
                    )
                    await self.bot.log_transaction(
                        ctx,
                        from_=1,
                        to=ctx.author.id,
                        subject="gambling",
                        data={"Amount": amount},
                        conn=conn,
                    )
            await ctx.send(
                _("{result[1]} It's **{result[0]}**! You won **${amount}**!").format(
                    result=result, amount=amount
                )
            )
        else:
            if amount > 0:
                async with self.bot.pool.acquire() as conn:
                    await conn.execute(
                        'UPDATE profile SET "money"="money"-$1 WHERE "user"=$2;',
                        amount,
                        ctx.author.id,
                    )
                    await self.bot.log_transaction(
                        ctx,
                        from_=ctx.author.id,
                        to=2,
                        subject="gambling",
                        data={"Amount": amount},
                        conn=conn,
                    )
            await ctx.send(
                _("{result[1]} It's **{result[0]}**! You lost **${amount}**!").format(
                    result=result, amount=amount
                )
            )

    @has_char()
    @commands.cooldown(1, 5, commands.BucketType.user)
    @commands.command(brief=_("Bet on a specific outcome of an n-sided dice."))
    @locale_doc
    async def bet(
            self,
            ctx,
            maximum: IntGreaterThan(1) = 6,
            tip: IntGreaterThan(0) = 6,
            money: IntFromTo(0, 100_000) = 0,
    ):
        _(
            """`[maximum]` - The amount of sides the dice will have, must be greater than 1; defaults to 6
            `[tip]` - The number to bet on, must be greater than 0 and lower than, or equal to `[maximum]`; defaults to 6
            `[money]` - The amount of money to bet, must be between 0 and 100,000; defaults to 0

            Bet on the outcome of an n-sided dice.

            You will win [maximum - 1] * [money] money if you are right and lose [money] if you are wrong.
            For example:
              `{prefix}bet 10 4 100`
              - Rolls a 10 sided dice
              - If the dice lands on 4, you will receive $900
              - If the dice lands on any other number, you will lose $100

            (This command has a cooldown of 5 seconds.)"""
        )
        if tip > maximum:
            return await ctx.send(
                _("Invalid Tip. Must be in the Range of `1` to `{maximum}`.").format(
                    maximum=maximum
                )
            )
        if money * (maximum - 1) > 100_000:
            return await ctx.send(_("Spend it in a better way. C'mon!"))
        if ctx.character_data["money"] < money:
            return await ctx.send(_("You're too poor."))
        randomn = random.randint(0, maximum)
        if randomn == tip:
            if money > 0:
                async with self.bot.pool.acquire() as conn:
                    await conn.execute(
                        'UPDATE profile SET "money"="money"+$1 WHERE "user"=$2;',
                        money * (maximum - 1),
                        ctx.author.id,
                    )
                    await self.bot.log_transaction(
                        ctx,
                        from_=1,
                        to=ctx.author.id,
                        subject="gambling",
                        data={"Amount": money * (maximum - 1)},
                        conn=conn,
                    )
            await ctx.send(
                _(
                    "You won **${money}**! The random number was `{num}`, you tipped"
                    " `{tip}`."
                ).format(num=randomn, tip=tip, money=money * (maximum - 1))
            )
            if maximum >= 100:
                await self.bot.public_log(
                    f"**{ctx.author}** won **${money * (maximum - 1)}** while betting"
                    f" with `{maximum}`. ({round(100 / maximum, 2)}% chance)"
                )
        else:
            if money > 0:
                async with self.bot.pool.acquire() as conn:
                    await conn.execute(
                        'UPDATE profile SET "money"="money"-$1 WHERE "user"=$2;',
                        money,
                        ctx.author.id,
                    )
                    await self.bot.log_transaction(
                        ctx,
                        from_=ctx.author.id,
                        to=2,
                        subject="gambling",
                        data={"Amount": money},
                        conn=conn,
                    )
            await ctx.send(
                _(
                    "You lost **${money}**! The random number was `{num}`, you tipped"
                    " `{tip}`."
                ).format(num=randomn, tip=tip, money=money)
            )

    @has_char()
    @commands.cooldown(1, 5, commands.BucketType.user)
    @commands.command(aliases=["bj"], brief=_("Play blackjack against the bot."))
    @locale_doc
    async def blackjack(self, ctx, amount: IntFromTo(0, 1000) = 0):
        _(
            """`[amount]` - The amount of money you bet, must be between 0 and 1000; defaults to 0

            Play a round of blackjack against the bot, controlled by reactions.
            The objective is to have a card value as close to 21 as possible, without exceeding it (known as bust).
            Having a card value of exactly 21 is known as a blackjack.

            \U00002934 Hit: Pick up another card
            \U00002935 Stand: stay at your current card value
            \U00002194 Split (if dealt two cards with the same value): Split your two cards into separate hands
            \U0001F501 Switch (if split): Change the focussed hand
            \U000023EC Double down: double the amount you bet in exchange for only one more card

            If a player wins, they will get the amount in cash. If they lose, they will lose that amount.
            If they win with a natural blackjack (first two dealt card get to a value of 21), the player wins 1.5 times the amount.

            (This command has a cooldown of 5 seconds.)"""
        )
        if amount > 0:
            if ctx.character_data["money"] < amount:
                return await ctx.send(_("You're too poor."))

            async with self.bot.pool.acquire() as conn:
                await conn.execute(
                    'UPDATE profile SET "money"="money"-$1 WHERE "user"=$2;',
                    amount,
                    ctx.author.id,
                )

                await self.bot.log_transaction(
                    ctx,
                    from_=ctx.author.id,
                    to=2,
                    subject="gambling",
                    data={"Amount": amount},
                    conn=conn,
                )

        bj = BlackJack(ctx, amount)
        await bj.run()

    @has_char()
    @commands.command(aliases=["doubleorsteal"], brief=_("Play double-or-steal"))
    @locale_doc
    async def dos(self, ctx, user: MemberWithCharacter = None):
        _(
            """`[user]` - A discord user with a character; defaults to anyone

            Play a round of double-or-steal against a player.

            Each round, a player can double the bet played for, or steal, removing the bet from the other player and giving it to the first."""
        )
        msg = await ctx.send(
            _("React with 💰 to play double-or-steal with {user}!").format(
                user=ctx.author
            )
        )

        def check(r, u):
            if user and user != u:
                return False
            return (
                    u != ctx.author
                    and not u.bot
                    and r.message.id == msg.id
                    and str(r.emoji) == "\U0001f4b0"
            )

        await msg.add_reaction("\U0001f4b0")

        try:
            r, u = await self.bot.wait_for("reaction_add", check=check, timeout=30)
        except asyncio.TimeoutError:
            return await ctx.send(_("Timed out."))

        if not await user_has_char(self.bot, u.id):
            return await ctx.send(_("{user} has no character.").format(user=u))
        money = 100
        users = (u, ctx.author)

        async with self.bot.pool.acquire() as conn:
            if not await self.bot.has_money(ctx.author, 100, conn=conn):
                return await ctx.send(
                    _("{user} is too poor to double.").format(user=user)
                )
            await conn.execute(
                'UPDATE profile SET "money"="money"-100 WHERE "user"=$1;', ctx.author.id
            )
            await self.bot.log_transaction(
                ctx,
                from_=ctx.author.id,
                to=2,
                subject="gambling",
                data={"Amount": 100},
                conn=conn,
            )

        while True:
            user, other = users
            try:
                action = await self.bot.paginator.Choose(
                    title=_("Double or steal ${money}?").format(money=money),
                    placeholder=_("Select an action"),
                    entries=[_("Double"), _("Steal")],
                    return_index=True,
                ).paginate(ctx, user=user)
            except self.bot.paginator.NoChoice:
                async with self.bot.pool.acquire() as conn:
                    await conn.execute(
                        'UPDATE profile SET "money"="money"+$1 WHERE "user"=$2;',
                        money,
                        other.id,
                    )
                    await self.bot.log_transaction(
                        ctx,
                        from_=1,
                        to=other.id,
                        subject="gambling",
                        data={"Amount": money},
                        conn=conn,
                    )
                return await ctx.send(_("Timed out."))

            if action:
                async with self.bot.pool.acquire() as conn:
                    await conn.execute(
                        'UPDATE profile SET "money"="money"+$1 WHERE "user"=$2;',
                        money,
                        user.id,
                    )
                    await self.bot.log_transaction(
                        ctx,
                        from_=other.id,
                        to=user.id,
                        subject="gambling",
                        data={"Amount": money},
                        conn=conn,
                    )
                return await ctx.send(
                    _("{user} stole **${money}**.").format(user=user, money=money)
                )
            else:
                new_money = money * 2
                async with self.bot.pool.acquire() as conn:
                    await conn.execute(
                        'UPDATE profile SET "money"="money"+$1 WHERE "user"=$2;',
                        money,
                        other.id,
                    )
                    if not await self.bot.has_money(user.id, new_money, conn=conn):
                        return await ctx.send(
                            _("{user} is too poor to double.").format(user=user)
                        )
                    await conn.execute(
                        'UPDATE profile SET "money"="money"-$1 WHERE "user"=$2;',
                        new_money,
                        user.id,
                    )
                await ctx.send(
                    _("{user} doubled to **${money}**.").format(
                        user=user, money=new_money
                    )
                )
                money = new_money
                users = (other, user)


async def setup(bot: Bot) -> None:
    await bot.add_cog(Gambling(bot))
