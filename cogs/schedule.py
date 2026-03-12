import math
from datetime import date, timedelta

import discord
from discord import app_commands
from discord.ext import commands

import database

# ─────────────────────────────── constants ────────────────────────────────── #

SLOT_EMOJIS = ["🌅", "☀️", "🌙"]
SLOT_NAMES  = ["午前", "午後", "夜"]
DAYS_PER_PAGE = 4
DAY_JP = ["月", "火", "水", "木", "金", "土", "日"]

# status int → display
STATUS_EMOJI = {0: "⬜", 1: "✅", 2: "🔺", 3: "❌"}
STATUS_LABEL = {0: "未入力", 1: "参加可", 2: "頑張ればいける", 3: "未定or参加不可"}
STATUS_STYLE = {
    0: discord.ButtonStyle.secondary,
    1: discord.ButtonStyle.success,
    2: discord.ButtonStyle.primary,
    3: discord.ButtonStyle.danger,
}

# ──────────────────────────── helper functions ────────────────────────────── #

def days_for_page(page: int, total_days: int) -> list[int]:
    start = page * DAYS_PER_PAGE
    return list(range(start, min(start + DAYS_PER_PAGE, total_days)))


def fmt_date(d: date) -> str:
    return f"{d.month}/{d.day}({DAY_JP[d.weekday()]})"


def poll_date(start_date: str, day_index: int) -> date:
    return date.fromisoformat(start_date) + timedelta(days=day_index)

# ──────────────────────────── embed builders ──────────────────────────────── #

def build_poll_embed(
    poll: dict,
    page: int,
    counts: dict,
    respondents: list[dict],
) -> discord.Embed:
    total_pages = math.ceil(poll["days"] / DAYS_PER_PAGE)
    embed = discord.Embed(title=f"📅 {poll['title']}", color=0x5865F2)

    day_blocks = []
    for day_idx in days_for_page(page, poll["days"]):
        d = poll_date(poll["start_date"], day_idx)
        slot_parts = []
        for slot_idx in range(3):
            c = counts.get((day_idx, slot_idx), {})
            av = c.get(1, 0)
            ma = c.get(2, 0)
            un = c.get(3, 0)
            slot_parts.append(f"{SLOT_EMOJIS[slot_idx]}{SLOT_NAMES[slot_idx]} ✅{av} 🔺{ma} ❌{un}")
        day_blocks.append(f"**{fmt_date(d)}**\n" + "　　".join(slot_parts))
    embed.description = "\n\n".join(day_blocks)

    if respondents:
        names = "　".join(r["username"] for r in respondents)
        embed.add_field(
            name=f"👥 回答者 ({len(respondents)}人)", value=names, inline=False
        )
    else:
        embed.add_field(name="👥 回答者", value="まだ誰も回答していません", inline=False)

    embed.set_footer(
        text=f"Poll ID: {poll['id']}　{page + 1}/{total_pages} ページ　開始日: {poll['start_date']}"
    )
    return embed


def build_vote_embed(poll: dict, page: int, user_votes: dict) -> discord.Embed:
    total_pages = math.ceil(poll["days"] / DAYS_PER_PAGE)

    day_blocks = []
    for day_idx in days_for_page(page, poll["days"]):
        d = poll_date(poll["start_date"], day_idx)
        slot_parts = []
        for slot_idx in range(3):
            s = user_votes.get((day_idx, slot_idx), 0)
            slot_parts.append(f"{SLOT_EMOJIS[slot_idx]}{SLOT_NAMES[slot_idx]} {STATUS_EMOJI[s]}")
        day_blocks.append(f"**{fmt_date(d)}**\n" + "　　".join(slot_parts))

    embed = discord.Embed(
        title=f"🗳️ あなたの回答 — {poll['title']}",
        description=(
            "⬜ 未入力 → ✅ 参加可 → 🔺 頑張ればいける → ❌ 未定or参加不可\n"
            "考えるのが面倒な日は未定のままでいいです。\n\n"
            + "\n\n".join(day_blocks)
        ),
        color=0x57F287,
    )
    embed.set_footer(text=f"{page + 1}/{total_pages} ページ　変更は即時保存されます")
    return embed

# ──────────────────────────── view factories ──────────────────────────────── #

def make_poll_view(poll_id: int, page: int, total_pages: int) -> discord.ui.View:
    """Main poll message buttons (nav + vote)."""
    view = discord.ui.View(timeout=None)

    view.add_item(discord.ui.Button(
        label="◀ 前のページ",
        style=discord.ButtonStyle.secondary,
        disabled=(page == 0),
        row=0,
        custom_id=f"nav:prev:{poll_id}:{page}",
    ))
    view.add_item(discord.ui.Button(
        label=f"{page + 1} / {total_pages} ページ",
        style=discord.ButtonStyle.secondary,
        disabled=True,
        row=0,
        custom_id=f"nav:label:{poll_id}:{page}",
    ))
    view.add_item(discord.ui.Button(
        label="次のページ ▶",
        style=discord.ButtonStyle.secondary,
        disabled=(page >= total_pages - 1),
        row=0,
        custom_id=f"nav:next:{poll_id}:{page}",
    ))
    view.add_item(discord.ui.Button(
        label="🗳️ 回答する",
        style=discord.ButtonStyle.primary,
        row=1,
        custom_id=f"nav:vote:{poll_id}",
    ))
    view.add_item(discord.ui.Button(
        label="🗑️ アンケートを削除",
        style=discord.ButtonStyle.danger,
        row=1,
        custom_id=f"nav:delete:{poll_id}",
    ))
    return view


def make_vote_view(
    poll_id: int,
    page: int,
    user_id: str,
    total_pages: int,
    user_votes: dict,
    start_date: str,
    total_days: int,
) -> discord.ui.View:
    """Ephemeral per-user voting view."""
    view = discord.ui.View(timeout=None)

    for row_num, day_idx in enumerate(days_for_page(page, total_days)):
        d = poll_date(start_date, day_idx)
        # Disabled date label
        view.add_item(discord.ui.Button(
            label=fmt_date(d),
            style=discord.ButtonStyle.secondary,
            disabled=True,
            row=row_num,
            custom_id=f"vote:label:{poll_id}:{day_idx}",
        ))
        for slot_idx in range(3):
            s = user_votes.get((day_idx, slot_idx), 0)
            view.add_item(discord.ui.Button(
                label=f"{SLOT_EMOJIS[slot_idx]} {SLOT_NAMES[slot_idx]} {STATUS_EMOJI[s]}",
                style=STATUS_STYLE[s],
                row=row_num,
                custom_id=f"vote:slot:{poll_id}:{day_idx}:{slot_idx}:{user_id}",
            ))

    # Navigation row (row 4)
    view.add_item(discord.ui.Button(
        label="◀ 前へ",
        style=discord.ButtonStyle.secondary,
        disabled=(page == 0),
        row=4,
        custom_id=f"vote:prev:{poll_id}:{page}:{user_id}",
    ))
    view.add_item(discord.ui.Button(
        label=f"{page + 1}/{total_pages}",
        style=discord.ButtonStyle.secondary,
        disabled=True,
        row=4,
        custom_id=f"vote:pagelabel:{poll_id}:{page}:{user_id}",
    ))
    view.add_item(discord.ui.Button(
        label="次へ ▶",
        style=discord.ButtonStyle.secondary,
        disabled=(page >= total_pages - 1),
        row=4,
        custom_id=f"vote:next:{poll_id}:{page}:{user_id}",
    ))
    view.add_item(discord.ui.Button(
        label="✅ 完了",
        style=discord.ButtonStyle.success,
        row=4,
        custom_id=f"vote:done:{poll_id}:{user_id}",
    ))
    return view

# ─────────────────────────── interaction handlers ─────────────────────────── #

async def handle_nav_interaction(interaction: discord.Interaction, db_path: str):
    """Handle nav:prev, nav:next, nav:vote, nav:delete."""
    parts = interaction.data["custom_id"].split(":")
    action = parts[1]

    if action == "label":
        await interaction.response.defer()
        return

    poll_id = int(parts[2])
    poll = await database.get_poll(db_path, poll_id)
    if not poll:
        await interaction.response.send_message(
            "このアンケートは存在しないか削除されました。", ephemeral=True
        )
        return

    total_pages = math.ceil(poll["days"] / DAYS_PER_PAGE)

    if action == "vote":
        user_id = str(interaction.user.id)
        user_votes = await database.get_user_votes(db_path, poll_id, user_id)
        view = make_vote_view(poll_id, 0, user_id, total_pages, user_votes, poll["start_date"], poll["days"])
        embed = build_vote_embed(poll, 0, user_votes)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    elif action in ("prev", "next"):
        current_page = int(parts[3])
        new_page = current_page - 1 if action == "prev" else current_page + 1
        counts = await database.get_aggregate_counts(db_path, poll_id)
        respondents = await database.get_respondents(db_path, poll_id)
        embed = build_poll_embed(poll, new_page, counts, respondents)
        view = make_poll_view(poll_id, new_page, total_pages)
        await interaction.response.edit_message(embed=embed, view=view)

    elif action == "delete":
        if str(interaction.user.id) != poll["creator_id"]:
            await interaction.response.send_message(
                "削除できるのは作成者のみです。", ephemeral=True
            )
            return
        await database.delete_poll(db_path, poll_id)
        await interaction.response.edit_message(
            content="🗑️ アンケートを削除しました。", embed=None, view=None
        )


async def handle_vote_interaction(interaction: discord.Interaction, db_path: str):
    """Handle vote:slot, vote:prev, vote:next, vote:done."""
    parts = interaction.data["custom_id"].split(":")
    action = parts[1]

    if action in ("label", "pagelabel"):
        await interaction.response.defer()
        return

    poll_id = int(parts[2])

    # Parse user_id from custom_id and verify ownership
    if action == "slot":
        day_idx   = int(parts[3])
        slot_idx  = int(parts[4])
        user_id   = parts[5]
    elif action in ("prev", "next"):
        page      = int(parts[3])
        user_id   = parts[4]
    elif action == "done":
        user_id   = parts[3]
    else:
        return

    if str(interaction.user.id) != user_id:
        await interaction.response.send_message(
            "これはあなたの回答フォームではありません。", ephemeral=True
        )
        return

    poll = await database.get_poll(db_path, poll_id)
    if not poll:
        await interaction.response.send_message(
            "このアンケートは存在しないか削除されました。", ephemeral=True
        )
        return

    total_pages = math.ceil(poll["days"] / DAYS_PER_PAGE)

    if action == "slot":
        await database.cycle_vote(
            db_path, poll_id, user_id, interaction.user.display_name, day_idx, slot_idx
        )
        current_page = day_idx // DAYS_PER_PAGE
        user_votes = await database.get_user_votes(db_path, poll_id, user_id)
        view = make_vote_view(poll_id, current_page, user_id, total_pages, user_votes, poll["start_date"], poll["days"])
        embed = build_vote_embed(poll, current_page, user_votes)
        await interaction.response.edit_message(embed=embed, view=view)

    elif action in ("prev", "next"):
        new_page = page - 1 if action == "prev" else page + 1
        user_votes = await database.get_user_votes(db_path, poll_id, user_id)
        view = make_vote_view(poll_id, new_page, user_id, total_pages, user_votes, poll["start_date"], poll["days"])
        embed = build_vote_embed(poll, new_page, user_votes)
        await interaction.response.edit_message(embed=embed, view=view)

    elif action == "done":
        # Update the main poll message to reflect latest votes
        if poll.get("message_id"):
            try:
                channel = interaction.client.get_channel(int(poll["channel_id"]))
                if channel is None:
                    channel = await interaction.client.fetch_channel(int(poll["channel_id"]))
                msg = await channel.fetch_message(int(poll["message_id"]))
                counts = await database.get_aggregate_counts(db_path, poll_id)
                respondents = await database.get_respondents(db_path, poll_id)
                new_embed = build_poll_embed(poll, 0, counts, respondents)
                new_view = make_poll_view(poll_id, 0, total_pages)
                await msg.edit(embed=new_embed, view=new_view)
            except (discord.NotFound, discord.Forbidden, Exception):
                pass  # Main message may have been deleted; ignore silently

        done_embed = discord.Embed(
            title="✅ 回答を保存しました",
            description="「🗳️ 回答する」ボタンでいつでも変更できます。",
            color=0x57F287,
        )
        await interaction.response.edit_message(embed=done_embed, view=None)

# ───────────────────────────────── the cog ────────────────────────────────── #

class ScheduleCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db_path: str = bot.db_path  # type: ignore[attr-defined]

    @app_commands.command(name="schedule", description="日程調整アンケートを作成します")
    @app_commands.describe(
        title="アンケートのタイトル",
        days="対象日数 (デフォルト: 10、最大: 30)",
    )
    async def schedule(self, interaction: discord.Interaction, title: str, days: int = 10):
        if not interaction.guild_id:
            await interaction.response.send_message(
                "このコマンドはサーバー内でのみ使用できます。", ephemeral=True
            )
            return
        if not 1 <= days <= 30:
            await interaction.response.send_message(
                "日数は 1〜30 で指定してください。", ephemeral=True
            )
            return

        await interaction.response.defer()

        poll_id = await database.create_poll(
            self.db_path,
            guild_id=str(interaction.guild_id),
            channel_id=str(interaction.channel_id),
            title=title,
            creator_id=str(interaction.user.id),
            start_date=date.today(),
            days=days,
        )

        poll = await database.get_poll(self.db_path, poll_id)
        total_pages = math.ceil(days / DAYS_PER_PAGE)
        counts = await database.get_aggregate_counts(self.db_path, poll_id)
        respondents = await database.get_respondents(self.db_path, poll_id)

        embed = build_poll_embed(poll, 0, counts, respondents)
        view = make_poll_view(poll_id, 0, total_pages)

        msg = await interaction.followup.send(embed=embed, view=view)
        await database.set_poll_message_id(self.db_path, poll_id, str(msg.id))


async def setup(bot: commands.Bot):
    await bot.add_cog(ScheduleCog(bot))
