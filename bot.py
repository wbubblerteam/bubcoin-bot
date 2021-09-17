#!/usr/bin/env python3

import json

import discord
from discord.ext import commands
from sqlalchemy import Column, Integer, Text
from sqlalchemy.orm import declarative_base
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession


__version__ = '0.1.0'

CONFIG_PATH = 'config.json'
DB_PATH = 'bubcoinbot.db'
DEFAULT_PREFIX = 'B$'
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
        self.add_cog(BubcoinBotCommands(self))

        self.engine = create_async_engine(f'sqlite+aiosqlite:///{DB_PATH}', echo=SQL_ECHO, future=True)
        self.session = AsyncSession(self.engine)

        super().__init__(*args, **kwargs)

    def close(self):
        self.session.close()
        super().close()


class BubcoinBotCommands(commands.Cog):
    def __init__(self, bot: BubcoinBot):
        self.bot = bot

    @commands.command()
    def myid(self, ctx: commands.Context):
        return await ctx.send(ctx.author.id)


def main():
    with open(CONFIG_PATH) as config_file:
        config = json.load(config_file)

    bubcoin_bot = BubcoinBot(command_prefix=DEFAULT_PREFIX)
    bubcoin_bot.run(config['token'])


if __name__ == '__main__':
    main()
