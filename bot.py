#!/usr/bin/env python3

"""
Copyright (c) 2021 JMcB
Not for use with any cryptocurrency or blockchain that is any of the following:
legitimate, commercial, high proof-of-work
"""


import json
from typing import Optional

import aiohttp
import discord
from discord.ext import commands
from sqlalchemy import Column, Integer, Text
from sqlalchemy.orm import declarative_base
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession


__version__ = '0.1.0a'

CONFIG_PATH = 'config.json'
DB_PATH = 'bubcoinbot.db'
SQL_ECHO = True
GITHUB_URL = 'https://github.com/wbubblerteam/bubcoin-bot'
DEFAULT_PREFIX = ('B$', 'b$', '$')
COIN = 100000000
RPC_PORT = 8332
RPC_USERNAME = 'user'
RPC_ID = 'bubcoinbot'


# orm mappings
Base = declarative_base()


class User(Base):
    __tablename__ = 'users'

    discord_id = Column(Integer, primary_key=True)
    bubcoin_address = Column(Text)
    # The discord id signed with the private key of the address
    bubcoin_signature = Column(Text)
    # Coin units in virtual wallet
    prettytinybubs = Column(Integer)


# bot stuff
class BubcoinBot(commands.Bot):
    def __init__(self, *args, **kwargs):
        self.aioh_session = aiohttp.ClientSession()
        self.sqla_engine = create_async_engine(f'sqlite+aiosqlite:///{DB_PATH}', echo=SQL_ECHO, future=True)
        self.sqla_session = AsyncSession(self.sqla_engine)

        super().__init__(*args, **kwargs)

        self.add_cog(BubcoinBotCommands(self))

    async def on_ready(self):
        print(f'Started as {self.user.name}.')

    async def close(self):
        await super().close()
        await self.sqla_session.close()
        await self.aioh_session.close()


class BubcoinBotCommands(commands.Cog):
    def __init__(self, bot: BubcoinBot):
        self.bot = bot
        self.rpc_url = f'http://127.0.0.1:{RPC_PORT}/'

    @commands.command(aliases=['github', 'git', 'source'])
    async def github_url(self, ctx: commands.Context):
        return await ctx.send(GITHUB_URL)

    @commands.command()
    async def invite(self, ctx: commands.Context):
        app_info = await self.bot.application_info()
        client_id = app_info.id

        permissions = discord.Permissions()
        permissions.update(send_message=True, read_message=True)

        invite_url = discord.utils.oauth_url(client_id, permissions, ctx.guild)
        await ctx.send(invite_url)

    @commands.command(aliases=['id', 'user_id'])
    async def discord_user_id(self, ctx: commands.Context, user: Optional[discord.User]):
        if user is None:
            user = ctx.author

        return await ctx.send(user.id)

    async def rpc_call(self, method: str, params: list[str]) -> dict:
        headers = {'content-type': 'text/plain'}
        json_data = {
            'jsonrpc': '1.0',
            'id': RPC_ID,
            'method': method,
            'params': params,
        }

        with self.bot.aioh_session.get(
            self.rpc_url, json=json_data, headers=headers, auth=aiohttp.BasicAuth(RPC_USERNAME)
        ) as response:
            return response.json()

    @commands.command(aliases=['verify'])
    async def verify_address(self, ctx: commands.Context, signature):
        pass


def main():
    print(f'Loading config from {CONFIG_PATH}.')
    with open(CONFIG_PATH) as config_file:
        config = json.load(config_file)

    bubcoin_bot = BubcoinBot(command_prefix=DEFAULT_PREFIX)
    print('Starting...')
    bubcoin_bot.run(config['token'])


if __name__ == '__main__':
    main()
