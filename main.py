import asyncio
import os
import discord
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()

DB_PATH = os.getenv("DB_PATH", "scheduler.db")


async def start_health_server():
    """Render の Web Service 用ヘルスチェックサーバー（ポートを開くだけ）。"""
    port = int(os.getenv("PORT", 8080))

    async def handle(reader, writer):
        writer.write(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nOK")
        await writer.drain()
        writer.close()

    server = await asyncio.start_server(handle, "0.0.0.0", port)
    async with server:
        await server.serve_forever()


class SchedulerBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        super().__init__(command_prefix="!", intents=intents)
        self.db_path = DB_PATH

    async def setup_hook(self):
        import database
        await database.init_db(self.db_path)
        await self.load_extension("cogs.schedule")

        sync_guild = os.getenv("SYNC_GUILD_ID")
        if sync_guild:
            guild = discord.Object(id=int(sync_guild))
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
            print(f"Commands synced to guild {sync_guild}")
        else:
            await self.tree.sync()
            print("Commands synced globally")

    async def on_interaction(self, interaction: discord.Interaction):
        """Route button interactions via custom_id prefix instead of view registry."""
        if interaction.type == discord.InteractionType.component:
            cid = interaction.data.get("custom_id", "")
            if cid.startswith("nav:"):
                from cogs.schedule import handle_nav_interaction
                await handle_nav_interaction(interaction, self.db_path)
                return
            elif cid.startswith("vote:"):
                from cogs.schedule import handle_vote_interaction
                await handle_vote_interaction(interaction, self.db_path)
                return
        await super().on_interaction(interaction)

    async def on_ready(self):
        print(f"Logged in as {self.user} ({self.user.id})")


async def main():
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        raise RuntimeError("DISCORD_TOKEN が設定されていません。.env ファイルを確認してください。")
    bot = SchedulerBot()
    async with asyncio.TaskGroup() as tg:
        tg.create_task(start_health_server())
        tg.create_task(bot.start(token))


if __name__ == "__main__":
    asyncio.run(main())
