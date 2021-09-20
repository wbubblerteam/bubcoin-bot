#!/usr/bin/env python3

"""Exchange for Bubcoin over Discord.

Copyright (c) 2021 JMcB
Not for use with any cryptocurrency or blockchain that is any of the following:
legitimate, commercial, high proof-of-work
"""


import json
from decimal import Decimal
from typing import Optional

import aiohttp
import discord
from discord.ext import commands
from sqlalchemy import Column, Integer, Text
from sqlalchemy.orm import declarative_base
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession


__version__ = '0.1.0a'

# todo: use replies instead of sends?
# todo: handle wallet passphrases

CONFIG_PATH = 'config.json'
DB_PATH = 'bubcoinbot.db'
SQL_ECHO = True
GITHUB_URL = 'https://github.com/wbubblerteam/bubcoin-bot'
BOT_PERMISSIONS = {
    'read_messages': True,
    'send_message': True,
}
DEFAULT_PREFIX = ('B$', 'b$', '$')
COIN = 100000000
MAX_MONEY = 1000 * COIN
RPC_PORT = 8332
RPC_USERNAME = 'user'
RPC_ID = 'bubcoinbot'


def coin(prettytinybubs: int) -> Decimal:
    return Decimal(prettytinybubs) / Decimal(COIN)


# orm mappings
Base = declarative_base()


class User(Base):
    """The SQL table for users, with discord id, address, and coins."""
    __tablename__ = 'users'

    discord_id = Column(Integer, primary_key=True, nullable=False)
    bubcoin_address = Column(Text)
    # The discord id signed with the private key of the address
    bubcoin_signature = Column(Text)
    # Coin units in virtual wallet
    prettytinybubs = Column(Integer, default=0)


# bot stuff
class CustomHelpCommand(commands.DefaultHelpCommand):
    def __init__(self, **kwargs):
        kwargs.setdefault('no_category', 'Help')
        super().__init__(**kwargs)

    def get_ending_note(self):
        return super().get_ending_note() + f'\n\nTo get started with Bubcoin Bot, try {self.context.prefix}verify.'


class BubcoinBot(commands.Bot):
    """Bot subclass to open and close the sqlalchemy orm and the aiohttp sessions, and load the main cog."""
    def __init__(self, *args, **kwargs):
        self.aioh_session = None
        self.sqla_engine = create_async_engine(f'sqlite+aiosqlite:///{DB_PATH}', echo=SQL_ECHO, future=True)
        self.sqla_session = AsyncSession(self.sqla_engine)

        super().__init__(help_command=CustomHelpCommand(), *args, **kwargs)

        self.add_cog(BubcoinBotCommands(self))

    async def on_ready(self):
        self.aioh_session = aiohttp.ClientSession()
        async with self.sqla_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        print(f'Started as {self.user.name}.')

    async def on_command_error(self, ctx: commands.Context, exception: Exception):
        if isinstance(exception, commands.MissingRequiredArgument):
            help_message = f'You used the command wrong (missing argument), try: \n{ctx.prefix}help {ctx.invoked_with}'
            await ctx.send(help_message)
        elif isinstance(exception.__cause__, aiohttp.ClientConnectorError):
            await ctx.send('Bubcoin Core RPC server not running, shutting down.')
            await self.close()
        else:
            await super().on_command_error(ctx, exception)

    async def close(self):
        await super().close()
        await self.sqla_session.close()
        await self.aioh_session.close()


class BubcoinBotCommands(commands.Cog):
    """Cog containing all the bot's commands, loaded by default."""
    def __init__(self, bot: BubcoinBot):
        self.bot = bot
        self.rpc_url = f'http://127.0.0.1:{RPC_PORT}/'
        self.pending_withdrawals = {}

        self.sqla_session = self.bot.sqla_session
        self.aioh_session = self.bot.aioh_session

    @commands.command(aliases=['github', 'git', 'source'])
    async def github_url(self, ctx: commands.Context):
        """Send the url to the code repo for the bot.

        Gets it from the GITHUB_URL constant.
        """
        return await ctx.send(GITHUB_URL)

    @commands.command(aliases=['invite'])
    async def invite_bot(self, ctx: commands.Context):
        """Send a discord bot invite for this bot.

        Uses the bot's current client id and some required permissions.
        """
        app_info = await self.bot.application_info()
        client_id = app_info.id

        permissions = discord.Permissions()
        permissions.update(**BOT_PERMISSIONS)

        invite_url = discord.utils.oauth_url(client_id, permissions, ctx.guild)
        await ctx.send(invite_url)

    @commands.command(aliases=['id', 'user_id', 'discord_user_id'])
    async def discord_id(self, ctx: commands.Context, user: Optional[discord.User]):
        """Get your discord user id.

        Used for signing and verifying your bubcoin address.
        You can also enable discord's developer options and right click yourself to get your id.
        """
        if user is None:
            user = ctx.author

        return await ctx.send(user.id)

    async def rpc_call(self, method: str, *params: str) -> dict:
        """Wrapper for calls to the Bubcoin Core RPC API."""
        headers = {'content-type': 'text/plain'}
        json_data = {
            'jsonrpc': '1.0',
            'id': RPC_ID,
            'method': method,
            'params': params,
        }

        async with self.aioh_session.get(
            self.rpc_url, json=json_data, headers=headers, auth=aiohttp.BasicAuth(RPC_USERNAME)
        ) as response:
            return await response.json()

    @commands.command(aliases=['verify'])
    async def verify_address(self, ctx: commands.Context, address: str, signature: str):
        """Add or change your verified Bubcoin wallet address.

        Args:
            address -- the Bubcoin wallet address
            signature -- your discord user id cryptographically signed with your Bubcoin wallet
        Example:
        b$verify bcrt1qdm8hufy56erp5mf5epqevw5u4mywn9j0tpm3ke \
IIib3x/iuYuhUxAeiDO2i+F3Kz4idLVNK5OlEwp3991WNWy9mTl4RZRGOw2weA3tlsDHYag3zKt9I3EOrjSgVTY=

        After you've added verified an address, you can deposit Bubcoin by sending it from your verified address
        to the bot's public wallet, and withdraw Bubcoin to your verified address.
        Signing your discord user id with your wallet's private key proves that you own it.
        To get your user id, use this bot's `discord_id` command.
        To sign it, use Bubcoin core:
        `bubcoin-cli signmessage <address> <message>`
        For example:
        `bubcoin-cli signmessage "bcrt1qdm8hufy56erp5mf5epqevw5u4mywn9j0tpm3ke" "329885271787307008"`
        """
        # todo: regex sanity checks for args

        address_validation = await self.rpc_call('validateaddress', address)
        valid_address = address_validation['isvalid']
        if not valid_address:
            return await ctx.send(f'Invalid address: {address}')

        verified_message = await self.rpc_call('verifymessage', address, signature, ctx.author.id)
        if not verified_message:
            return await ctx.send('Invalid cryptographic signature.')

        user = await self.sqla_session.get(User, ctx.author.id)
        async with self.sqla_session.begin():
            if user is None:
                user = User(ctx.author.id)
                await self.sqla_session.add(user)
            prev_address = user.bubcoin_address
            user.bubcoin_address = address
            user.bubcoin_signature = signature

        message = f'Your new verified Bubcoin address is {address}.'
        if prev_address is not None:
            message = f'Your previous address was {prev_address}.\n' + message
        return await ctx.send(message)

    async def amount_check(self, ctx: commands.Context, amount_prettytinybubs: int, action: str) -> str:
        """Check if an amount of Bubcoin is valid and if the ctx.author has that amount.

        Args:
            ctx -- command context, used for getting user id, and command prefix for help strings
            amount_prettytinybubs -- amount of Bubcoin to check
            action -- a word like 'send' or 'withdraw', for the help strings
        Returns an empty string if checks passed, or a string detailing what went wrong, to give to the user,
        if a check failed.
        """
        # sanity checks
        if amount_prettytinybubs == 0:
            return f"There's no point trying to {action} 0 Bubcoin."

        if amount_prettytinybubs > MAX_MONEY:
            return (
                f"You can't {action} more than the maximum possible number of Bubcoins. \n"
                f'Max Bubcoins: \n₿{coin(MAX_MONEY)}'
            )

        # check if user has an account
        user = await self.sqla_session.get(User, ctx.author.id)
        if user is None:
            return f'You do not have a Bubcoin Bot account. Try: \n{ctx.prefix}verify'

        # check if user has enough money
        if amount_prettytinybubs > user.prettytinybubs:
            return (
                'Insufficient funds. \n'
                f'You have: \n₿{coin(user.prettytinybubs)}\n'
                f'You would need an additional: ₿{coin(amount_prettytinybubs - user.prettytinybubs)}\n'
            )

        # return an empty string if all checks are ok
        return ''

    @commands.command(aliases=['send_bubcoins', 'send', 'transfer'])
    async def send_bubcoin(self, ctx: commands.Context, user: discord.User, amount: Decimal):
        """Send Bubcoin to another user's account.

        Args:
            user -- the Bubcoin Bot discord user to send Bubcoin to
            amount -- the number of Bubcoin to send, as a decimal number
        Example:
        b$send @Wbubbler 10.0

        This transfers virtual Bubcoin between your Bubcoin Bot accounts.
        To withdraw real Bubcoin from your account, use the `withdraw` command.
        To deposit real Bubcoin into your account, use the `deposit` command.
        """
        amount_prettytinybubs = int(amount * COIN)
        failure = await self.amount_check(ctx, amount_prettytinybubs, 'send')
        if failure:
            return await ctx.send(failure)

        # check passed, send the money
        sender = await self.sqla_session.get(User, ctx.author.id)
        recipient = await self.sqla_session.get(User, user.id)
        async with self.sqla_session.begin():
            # make an account for recipient if needed
            if recipient is None:
                recipient = User(user.id)
                self.sqla_session.add(recipient)
            sender.prettytinybubs -= amount_prettytinybubs
            recipient.prettytinybubs += amount_prettytinybubs
        return await ctx.send(
            f'Transaction successful! \nYour new balance is: \n₿{coin(sender.prettytinybubs)}'
        )

    @commands.group(aliases=['withdraw'])
    async def withdraw_bubcoin(self, ctx: commands.Context, amount: Decimal, confirm: bool = False):
        """Withdraw Bubcoin from your account.

        Args:
            amount -- the number of Bubcoin to withdraw, as a decimal number
            confirm -- skip manual confirmation

        Sends real Bubcoin from the bot's wallet to your verified wallet address.
        If you leave out the `confirm` argument, you will be asked for confirmation.
        """
        if ctx.invoked_subcommand is not None:
            return

        amount_prettytinybubs = int(amount * COIN)
        failure = await self.amount_check(ctx, amount_prettytinybubs, 'withdraw')
        if failure:
            return await ctx.send(failure)

        # check if user has verified address
        user = await self.sqla_session.get(User, ctx.author.id)
        if user.bubcoin_address is None:
            return await ctx.send(
                'You do not have a verified Bubcoin address to withdraw to. Try:'
                f' \n{ctx.prefix}verify'
            )

        # checks passed, now confirmation
        if not confirm:
            self.pending_withdrawals[ctx.author.id] = amount
            return await ctx.send(
                'Withdrawal pending confirmation.'
                f' \nAddress: \n{user.bubcoin_address}'
                f' \nAmount: \n₿{amount}'
                f' \nNew balance: \n₿{coin(user.prettytinybubs - amount_prettytinybubs)}'
            )

        # withdraw the money
        async with self.sqla_session.begin():
            user.prettytinybubs -= amount_prettytinybubs

            rpc_params = [
                # dummy string
                '',
                # problematic precision?
                {user.bubcoin_address: amount},
                # dummy value
                6,
                # comment
                f'Withdrawal by {ctx.author.name}#{ctx.author.discriminator} ({ctx.author.id}).'
            ]
            await self.rpc_call('sendmany', *rpc_params)

        return await ctx.send(
            'Withdrawal successful! \n'
            f'Your new balance is: \n₿{coin(user.prettytinybubs)}'
        )

    @withdraw_bubcoin.command(name='confirm')
    async def withdraw_bubcoin_confirm(self, ctx: commands.Context):
        if ctx.author.id not in self.pending_withdrawals:
            return await ctx.send('No withdrawals pending confirmation!')

        return await ctx.invoke(
            self.withdraw_bubcoin,
            amount=self.pending_withdrawals[ctx.author.id], confirm=True
        )


def main():
    """Main function to load config and run the bot."""
    print(f'Loading config from {CONFIG_PATH}..')
    with open(CONFIG_PATH) as config_file:
        config = json.load(config_file)

    bubcoin_bot = BubcoinBot(command_prefix=DEFAULT_PREFIX)
    print('Starting...')
    bubcoin_bot.run(config['token'])


if __name__ == '__main__':
    main()
