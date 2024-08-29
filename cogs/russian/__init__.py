"""
The IdleRPG Discord Bot
Copyright (C) 2018-2021 Diniboy and Gelbpunkt
Copyright (C) 2024 Lunar (discord itslunar.)

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

import discord
import asyncio
import random
from discord.ext import commands
from utils.checks import has_char
from utils.i18n import _, locale_doc


class russian(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.participants = []
        self.is_game_running = False
        self.roundnum = 1
        self.bettotal = 0
        self.counter = 0
        self.betamount = 0
        self.joined_players = set()
        self.gamestarted = False
        self.single = False

    @has_char()
    @commands.command()
    async def join(self, ctx):

        if not self.gamestarted:
            await ctx.send("There is no game running. You can't join now.")
            return

        if self.is_game_running:
            await ctx.send("A game is already running. You can't join now.")
            return

        if ctx.author in self.joined_players:
            await ctx.send(f"{ctx.author.mention}, you have already joined this game.")
            return

        if self.bettotal > 0:
            if self.counter == 0:
                self.betamount = self.bettotal
                self.counter = 1
            # Check the player's balance
            async with self.bot.pool.acquire() as conn:
                user_balance = await conn.fetchval(
                    'SELECT "money" FROM profile WHERE "user" = $1;',
                    ctx.author.id
                )

            if user_balance < self.betamount:
                await ctx.send(f"{ctx.author.mention}, you are too poor.")
                return

            # Deduct the bet amount from the player's profile
            async with self.bot.pool.acquire() as conn:
                await conn.execute(
                    'UPDATE profile SET "money"="money" - $1 WHERE "user"=$2;',
                    self.betamount, ctx.author.id
                )
            await ctx.send(f"{ctx.author.mention} has joined the game and paid a bet of {self.betamount}.")
            self.bettotal = self.bettotal + self.betamount
            self.participants.append(ctx.author)
            self.joined_players.add(ctx.author)

        else:
            await ctx.send(f"{ctx.author.mention} has joined the game!")
            self.participants.append(ctx.author)
            self.joined_players.add(ctx.author)

    @has_char()
    @commands.command(aliases=["rr", "gungame"], brief=_("Play Russian Roulette"))
    @locale_doc
    async def russianroulette(self, ctx, bet: int = 0):
        _(
            """`<amount>` - the amount of money to bid

            Start a game of Russian Roulette.

            Players take turns pulling the trigger while pointing the gun at their own head or another player's head, with the hope of avoiding the live round"""
        )
        if self.single:
            await ctx.send("A game is already running")
            return

        if bet < 0:
            await ctx.send(f"{ctx.author.mention} your bet must be above 0!")
            return
        if bet > 0:
            # Deduct the bet amount from the player's profile
            async with self.bot.pool.acquire() as conn:
                user_balance = await conn.fetchval(
                    'SELECT "money" FROM profile WHERE "user" = $1;',
                    ctx.author.id
                )

            if user_balance < bet:
                await ctx.send(f"{ctx.author.mention}, you don't have enough money to cover the bet of **${bet}**.")
                return
            else:
                self.single = True
                async with self.bot.pool.acquire() as conn:
                    await conn.execute(
                        'UPDATE profile SET "money"="money" - $1 WHERE "user"=$2;',
                        bet, ctx.author.id
                    )
                    self.bettotal = bet
                    winnings = self.bettotal
                await ctx.send(f"Russian Roulette game has started with a entry fee of **${bet}!** Wait for 2 "
                               f"minutes for players to join.")
                self.gamestarted = True
                self.joined_players.add(ctx.author)
        else:
            await ctx.send("**Russian Roulette game has started!** Players have 2 minutes to join using **$join**.")
            self.gamestarted = True
            self.joined_players.add(ctx.author)

        self.participants.append(ctx.author)
        await asyncio.sleep(120)  # Wait for 2 minutes

        if len(self.participants) < 2:
            await ctx.send("Not enough players to start the game.")
            async with self.bot.pool.acquire() as conn:
                await conn.execute(
                    'UPDATE profile SET "money"="money"+$1 WHERE "user"=$2;',
                    bet, ctx.author.id
                )
                self.joined_players.clear()
                bet = 0
                self.single = False
            return
        # Automatically add the player who started the game
        if ctx.author not in self.participants:
            self.participants.append(ctx.author)
            await ctx.send(f"{ctx.author.mention} has joined the game!")

        random.shuffle(self.participants)
        remaining = len(self.participants)
        await ctx.send(f"There are {remaining} players!")
        self.is_game_running = True  # Set the flag
        chambers = [False] * 5 + [True]
        random.shuffle(chambers)
        await self.announce_round(ctx)

        while len(self.participants) > 1:

            # await asyncio.sleep(5)  # Wait for players to react

            players_to_remove = []

            # Use a flag to track if anyone was eliminated in this round
            player_eliminated = False
            other_player = None
            try:
                for player in self.participants.copy():
                    await asyncio.sleep(5)
                    await ctx.send(f"It's {player.mention}'s turn! They pick up the gun and turn it towards their head and "
                                   f"slowly pulls the trigger...")
                    await asyncio.sleep(4)  # Simulate suspense

                    chamber_drawn = chambers.pop(0)

                    if chamber_drawn:
                        await asyncio.sleep(2)  # Simulate suspense
                        if len(self.participants) == 2 and random.random() < 0.25:
                            other_player = [p for p in self.participants if p != player][0]
                            embed = discord.Embed(
                                title="BANG!",
                                description=f"{other_player.mention} has been shot by {player.mention}!",
                                color=discord.Color.red()
                            )
                            embed.set_image(url="https://media.tenor.com/ggBL-mf1-swAAAAC/guns-anime.gif")
                            await asyncio.sleep(3)  # Simulate suspense
                            await ctx.send(embed=embed)
                            players_to_remove.append(other_player)
                            self.participants.remove(other_player)
                            player_eliminated = True
                            shotother = 1
                        else:
                            embed = discord.Embed(
                                title="BANG!",
                                description=f"{player.mention} has shot themselves in the face!",
                                color=discord.Color.red()
                            )
                            embed.set_image(url="https://i.ibb.co/kKn0zQs/ezgif-4-51fcaad25e.gif")
                            await asyncio.sleep(3)  # Simulate suspense
                            await ctx.send(embed=embed)
                            players_to_remove.append(player)
                            self.participants.remove(player)
                            player_eliminated = True
                            shotother = 0

                    else:
                        await asyncio.sleep(3)  # Simulate suspense
                        # await ctx.send(f"**Click!** {player.mention} has survived this round.")
                        embed = discord.Embed(
                            title="The Gun Clicks!",
                            description=f"{player.mention} has survived this round and passes the gun the next player!",
                            color=discord.Color.green()
                        )
                        # embed.set_image(url="https://i.ibb.co/nrgq8y8/ezgif-4-b0beb6f344.gif")
                        await ctx.send(embed=embed)
                        await asyncio.sleep(3)  # Simulate suspense

                    if player_eliminated:
                        if shotother == 1:
                            if other_player is not None:
                                await ctx.send(f"Round over! {other_player.mention} was killed!")
                        else:
                            await ctx.send(f"Round over! {player.mention} was killed!")
                            remaining = len(self.participants)
                            if len(self.participants) > 1:
                                await ctx.send(f"There are {remaining} player(s) remaining")

                            # Check if other_player has a value before accessing it

                        if len(self.participants) == 1:
                            winner = self.participants[0]
                            if bet > 0:
                                async with self.bot.pool.acquire() as conn:
                                    await conn.execute(
                                        'UPDATE profile SET "money"="money"+$1 WHERE "user"=$2;',
                                        self.bettotal, winner.id
                                    )
                                winnings = self.bettotal - winnings
                                await ctx.send(
                                    f"Congratulations {winner.mention}! You are the last one standing and won **${winnings}**.")
                                self.joined_players.clear()
                                self.gamestarted = False
                                self.roundnum = 0
                                self.single = False
                            else:
                                await ctx.send(
                                    f"Congratulations {winner.mention}! You are the last one standing. **Game over!**")
                            self.gamestarted = False
                            self.participants.clear()
                            self.joined_players.clear()
                            self.roundnum = 1
                            self.single = False
                            break
                        else:
                            self.roundnum = self.roundnum + 1
                            await self.announce_round(ctx)
                            chambers = [False] * 5 + [True]
                            random.shuffle(chambers)
                            player_eliminated = False

                if not self.participants:
                    break  # If all players are eliminated
            except Exception as e:
                self.single = False
                await ctx.send(f"An error occurred: {e}")

        self.is_game_running = False
        self.single = False

    async def announce_round(self, ctx):
        embed = discord.Embed(
            title=f"Round {self.roundnum}",
            description="Surviving players automatically move to the next round. Round will start in 5 seconds..",
            color=discord.Color.green()
        )
        embed.set_image(url="https://media.tenor.com/fklGVnlUSFQAAAAd/russian-roulette.gif")
        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(russian(bot))
