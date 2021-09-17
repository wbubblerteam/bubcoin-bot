#!/usr/bin/env python3

"""
Copyright (c) 2021 JMcB
Not for use with any cryptocurrency or blockchain that is any of the following:
legitimate, commercial, high proof-of-work
"""


import json
from typing import Optional

import discord
from discord.ext import commands
from sqlalchemy import Column, Integer, Text
from sqlalchemy.orm import declarative_base
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession


__version__ = '0.1.0a'

CONFIG_PATH = 'config.json'
DB_PATH = 'bubcoinbot.db'
DEFAULT_PREFIX = ('B$', 'b$', '$')
SQL_ECHO = True


# orm mappings
Base = declarative_base()


class User(Base):
    __tablename__ = 'users'

    discord_id = Column(Integer, primary_key=True)
    bubcoin_address = Column(Text)
    # The discord id signed with the private key of the address
    bubcoin_signature = Column(Text)


# bot stuff
class BubcoinBot(commands.Bot):
    def __init__(self, *args, **kwargs):
        self.engine = create_async_engine(f'sqlite+aiosqlite:///{DB_PATH}', echo=SQL_ECHO, future=True)
        self.session = AsyncSession(self.engine)

        super().__init__(*args, **kwargs)

        self.add_cog(BubcoinBotCommands(self))

    async def on_ready(self):
        print(f'Started as {self.user.name}.')

    async def close(self):
        await super().close()
        await self.session.close()


class BubcoinBotCommands(commands.Cog):
    def __init__(self, bot: BubcoinBot):
        self.bot = bot

    @commands.command(aliases=['id'])
    async def userid(self, ctx: commands.Context, user: Optional[discord.User]):
        if user is None:
            user = ctx.author

        return await ctx.send(user.id)


def main():
    print(f'Loading config from {CONFIG_PATH}.')
    with open(CONFIG_PATH) as config_file:
        config = json.load(config_file)

    bubcoin_bot = BubcoinBot(command_prefix=DEFAULT_PREFIX)
    print('Starting...')
    bubcoin_bot.run(config['token'])


if __name__ == '__main__':
    main()
