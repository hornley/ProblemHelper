import discord
from discord import app_commands

token = ''

intents = discord.Intents.default()
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

problems_channel_id = None
problems_thread_id = {"Easy": None}
ssh_thread_id = None
solutions_thread_id = None
templates_thread_id = None
submissions_thread_id = None
database_thread_id = None
ongoing_users = {}

CONST_MAX_PROBLEMS_PER_PAGE = 5
CONST_GUILD_ID = None


class UserData:
    def __init__(self, file, data):
        self.problem_name = data[0]
        self.language_attempt = data[1]
        self.solved = data[2]
        self.status = data[3]
        self.file = file


async def save():
    guild = client.get_guild(CONST_GUILD_ID)
    channel = guild.get_channel(problems_channel_id)
    database_thread = discord.utils.get(channel.threads, id=database_thread_id)
    await database_thread.purge()
    print(database_thread.message_count)
    for user_id in ongoing_users.keys():
        datas = ongoing_users[user_id]
        data: UserData
        for data in datas:
            embed = discord.Embed(title=user_id, color=discord.Color.green())
            embed.add_field(name="Problem Name", value=data.problem_name, inline=False)
            embed.add_field(name="Language Attempt", value=data.language_attempt, inline=False)
            embed.add_field(name="Solved", value=data.solved, inline=False)
            embed.add_field(name="Submission Status", value=data.status, inline=False)
            if data.file is not None:
                file = await data.file.to_file()
                await database_thread.send(embed=embed, file=file)
            else:
                await database_thread.send(embed=embed)


async def load():
    guild = client.get_guild(CONST_GUILD_ID)
    channel = guild.get_channel(problems_channel_id)
    database_thread = discord.utils.get(channel.threads, id=database_thread_id)
    submissions_thread = discord.utils.get(channel.threads, id=submissions_thread_id)
    await submissions_thread.purge()
    async for message in database_thread.history():
        embed = message.embeds[0]
        user_id = int(embed.title)
        if user_id not in ongoing_users.keys():
            ongoing_users[user_id] = []
        file = message.attachments[0] if len(message.attachments) > 0 else None
        Data = UserData(file, [field.value for field in embed.fields])
        ongoing_users[user_id].append(Data)

        if Data.status == "For checking":
            member = await client.get_guild(CONST_GUILD_ID).fetch_member(user_id)
            embed = discord.Embed(title=Data.problem_name, color=discord.Color.blurple())
            embed.add_field(name="User:", value=member.name, inline=False)
            embed.add_field(name="Language:", value=Data.language_attempt, inline=False)
            embed.add_field(name="Status:", value=Data.status, inline=False)
            msg = await submissions_thread.send(embed=embed, file=await file.to_file())
            await msg.edit(view=SubmissionUI(member, msg, Data))


class SubmissionUI(discord.ui.View):
    def __init__(self, user: discord.Member, msg: discord.Message, data: UserData):
        super().__init__()
        self.user = user
        self.msg = msg
        self.data = data
        self.timeout = None

    @discord.ui.button(label="Approve", style=discord.ButtonStyle.green, emoji="✅")
    async def aprroveButton(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        ongoing_users[self.user.id].remove(self.data)
        self.data.status = "Approved"
        ongoing_users[self.user.id].append(self.data)
        await self.user.send(f"## Your submission for {self.data.problem_name} has been approved!")
        await self.msg.delete()
        await save()

    @discord.ui.button(label="Deny", style=discord.ButtonStyle.red, emoji="❎")
    async def declineButton(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        ongoing_users[self.user.id].remove(self.data)
        self.data.status = "Denied"
        ongoing_users[self.user.id].append(self.data)
        await self.user.send(f"## Your submission for {self.data.problem_name} is denied!")
        await self.msg.delete()
        await save()


class ProblemUI(discord.ui.View):
    def __init__(self, user: discord.Member, problem_name: str, language: str):
        super().__init__()
        self.user = user
        self.problem_name = problem_name
        self.attempted = False
        self.solved = False
        self.language = language
        self.timeout = None

    @discord.ui.button(label="Try Problem", style=discord.ButtonStyle.blurple, emoji="🎯")
    async def tryProblemButton(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Check if user is already trying to solve a problem
        data: UserData
        if interaction.user.id in ongoing_users.keys():
            for data in ongoing_users[interaction.user.id]:
                if data.status == "For checking":
                    await interaction.response.send_message(f"## You are already attempting a different problem "
                                                            f"({data.problem_name})!\n"
                                                            f"Use command /problem-cancel to cancel attempt.",
                                                            ephemeral=True)
                    return

        self.attempted = True
        channel = interaction.guild.get_channel(problems_channel_id)
        templates_thread = discord.utils.get(channel.threads, id=templates_thread_id)

        if interaction.user.id not in ongoing_users.keys():
            ongoing_users[interaction.user.id] = []

        ongoing_users[interaction.user.id].append(UserData(None, [self.problem_name, self.language, self.solved, "To submit"]))

        # Template
        message: discord.Message
        async for message in templates_thread.history(oldest_first=True):
            title = message.content[2:message.content.find('\n')]
            if title.find(self.problem_name) != -1 and title.find(self.language) != -1:
                await interaction.response.send_message(message.content +
                                                        "\n## Use /submit (file) to submit your solution file attempt for approval!",
                                                        ephemeral=True, suppress_embeds=True)
                await save()
                return

        await interaction.response.send_message(f"## No template found for: {self.problem_name} ({self.language})",
                                                ephemeral=True)
        await save()

    @discord.ui.button(label="Show Solution", style=discord.ButtonStyle.green, emoji="💡")
    async def showSolutionButton(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.attempted:
            await interaction.response.send_message("## You have not yet attempted this problem!")
            return

        channel = interaction.guild.get_channel(problems_channel_id)
        solutions_thread = discord.utils.get(channel.threads, id=solutions_thread_id)
        ssh_thread = discord.utils.get(channel.threads, id=ssh_thread_id)

        message: discord.Message
        async for message in solutions_thread.history(oldest_first=True):
            title = message.content[2:message.content.find('\n')]
            if title.find(self.problem_name) != -1 and title.find(self.language) != -1:
                await interaction.response.send_message(message.content, ephemeral=True, suppress_embeds=True)
                return

        # Logging
        embed = discord.Embed(title=self.problem_name, color=discord.Color.blurple())
        embed.add_field(name="User:", value=self.user.name, inline=False)
        embed.add_field(name="Language:", value=self.language, inline=False)
        embed.add_field(name="Solved:", value=self.solved, inline=False)
        await ssh_thread.send(embed=embed)


class ProblemsUI(discord.ui.View):
    def __init__(self, thread: discord.Thread, msg: discord.Message, max: int):
        super().__init__()
        self.thread = thread
        self.msg = msg
        self.page = 1
        self.max = max
        self.timeout = None

    @discord.ui.button(label="Back", style=discord.ButtonStyle.green, emoji="◀️")
    async def backButton(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.page == 1:
            return
        await interaction.response.send_message("omsim")

    @discord.ui.button(label="Next", style=discord.ButtonStyle.green, emoji="▶️")
    async def nextButton(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.page > self.max:
            return
        embed = discord.Embed(title="Easy", color=discord.Color.dark_red())
        i = 1
        async for message in self.thread.history():
            if i >= 1 + CONST_MAX_PROBLEMS_PER_PAGE * self.page:
                title = message.content[2:message.content.find('\n')]
                embed.add_field(name=f"{i}: " + title, value=f"[Open]({message.jump_url})", inline=False)
            i += 1
        self.page += 1
        await self.msg.edit(embed=embed)


class CancelUI(discord.ui.View):
    def __init__(self, data: UserData):
        super().__init__()
        self.data = data
        self.timeout = None

    @discord.ui.button(label="Yes", style=discord.ButtonStyle.green, emoji="✅")
    async def yesButton(self, interaction: discord.Interaction, button: discord.ui.Button):
        ongoing_users[interaction.user.id].remove(self.data)
        self.data.status = "Cancelled"
        ongoing_users[interaction.user.id].append(self.data)
        await interaction.response.send_message(f"## Problem attempt for {self.data.problem_name} successfully cancelled.", ephemeral=True)
        await save()

    @discord.ui.button(label="No", style=discord.ButtonStyle.red, emoji="❎")
    async def noButton(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(f"## Problem attempt for {self.data.problem_name} not cancelled.", ephemeral=True)


@tree.command(
    name="submit",
    description="Submit my solution",
    guild=discord.Object(id=CONST_GUILD_ID)
)
@app_commands.describe(file="The file of your solution.")
async def submit_solution(interaction: discord.Interaction, file: discord.Attachment):
    data: UserData
    for data in ongoing_users[interaction.user.id]:
        if data.status == "To submit":
            ongoing_users[interaction.user.id].remove(data)
            data.file = file
            username = interaction.user.name
            data.status = "For checking"
            file_to_send = await data.file.to_file()
            ongoing_users[interaction.user.id].append(data)

            embed = discord.Embed(title=data.problem_name, color=discord.Color.blurple())
            embed.add_field(name="User:", value=username, inline=False)
            embed.add_field(name="Language:", value=data.language_attempt, inline=False)
            embed.add_field(name="Status:", value=data.status, inline=False)

            # Send file to the submission thread
            channel = interaction.guild.get_channel(problems_channel_id)
            submissions_thread = discord.utils.get(channel.threads, id=submissions_thread_id)
            msg = await submissions_thread.send(embed=embed, file=file_to_send)
            await msg.edit(view=SubmissionUI(interaction.user, msg, data))
            await interaction.response.send_message("## Submission successful!", ephemeral=True)
            await save()
            return


@tree.command(
    name="problems-list",
    description="Shows a list of the available problems of your chosen difficulty.",
    guild=discord.Object(id=CONST_GUILD_ID)
)
@app_commands.choices(difficulty=[
    app_commands.Choice(name='Easy', value="Easy")
])
async def get_list_of_problems(interaction, difficulty: app_commands.Choice[str]):
    channel = interaction.guild.get_channel(problems_channel_id)
    thread = discord.utils.get(channel.threads, id=problems_thread_id[difficulty.value])
    embed = discord.Embed(title="Easy", color=discord.Color.dark_red())
    message: discord.Message
    i = 1
    async for message in thread.history(oldest_first=True):
        if i <= CONST_MAX_PROBLEMS_PER_PAGE:
            title = message.content[2:message.content.find('\n')]
            embed.add_field(name=f"{i}: " + title, value="", inline=False)
        i += 1
    await interaction.response.send_message(embed=embed, ephemeral=True)
    msg = await interaction.original_response()
    await msg.edit(view=ProblemsUI(thread, msg, 1 + i // 3))


@tree.command(
    name="problems-choose",
    description="Choose a problem with the required parameters/arguments.",
    guild=discord.Object(id=CONST_GUILD_ID)
)
@app_commands.choices(difficulty=[
    app_commands.Choice(name='Easy', value="Easy")
])
@app_commands.describe(problem_number="The number of the problem.")
@app_commands.describe(language="PL to be used to solve the problem.")
async def choose_problem(interaction: discord.Interaction, difficulty: app_commands.Choice[str], problem_number: int,
                         language: str):
    channel = interaction.guild.get_channel(problems_channel_id)
    thread = discord.utils.get(channel.threads, id=problems_thread_id[difficulty.value])
    message: discord.Message
    i = 1
    async for message in thread.history(oldest_first=True):
        if i == problem_number:
            title = message.content[2:message.content.find('\n')]
            await interaction.response.send_message(message.content, ephemeral=True, suppress_embeds=True,
                                                    view=ProblemUI(interaction.user, title, language))
            return
        i += 1
    embed = discord.Embed(title="Error", description=f"Problem# {problem_number} does not exist in {difficulty.value}.",
                          color=discord.Color.dark_red())
    await interaction.response.send_message(embed=embed, ephemeral=True)


@tree.command(
    name="purge-database",
    description="Purge Database.",
    guild=discord.Object(id=CONST_GUILD_ID)
)
async def cancel_problem(interaction: discord.Interaction):
    guild = client.get_guild(CONST_GUILD_ID)
    channel = guild.get_channel(problems_channel_id)
    database_thread = discord.utils.get(channel.threads, id=database_thread_id)
    ongoing_users.clear()
    await database_thread.purge()


@tree.command(
    name="quit",
    description="Quit Bot.",
    guild=discord.Object(id=CONST_GUILD_ID)
)
async def cancel_problem(interaction: discord.Interaction):
    if interaction.user.id == "REPLACE THIS STRING WITH AUTHOR ID":
        await interaction.response.send_message("Bot is shutting down.")
        quit()


@tree.command(
    name="problem-cancel",
    description="Cancel current problem attempt.",
    guild=discord.Object(id=CONST_GUILD_ID)
)
async def cancel_problem(interaction: discord.Interaction):
    if interaction.user.id not in ongoing_users.keys():
        await interaction.response.send_message("## You have no ongoing solving attempt!", ephemeral=True)
        return

    for data in ongoing_users[interaction.user.id]:
        if data.status == "For checking" or data.status == "To submit":
            embed = discord.Embed(title="Confirmation", description=f"Do you wish to cancel your attempt for {data.problem_name}?",
                                  color=discord.Color.dark_red())
            await interaction.response.send_message(embed=embed, ephemeral=True, view=CancelUI(data))
            return

    await interaction.response.send_message("## You have no ongoing solving attempt!", ephemeral=True)


# @tree.command(
#     name="problem-attempt",
#     description="View current problem attempt.",
#     guild=discord.Object(id=CONST_GUILD_ID)
# )
# async def view_problem_attempt(interaction: discord.Interaction):
#     if interaction.user.id not in ongoing_users.keys():
#         return
#
#     for data in ongoing_users[interaction.user.id]:
#         if data.status == "For checking" or data.status == "To submit":
#             embed = discord.Embed(title="Confirmation", description=f"Do you wish to cancel your attempt for {data.problem_name}?",
#                                   color=discord.Color.dark_red())
#             await interaction.response.send_message(embed=embed, ephemeral=True, view=CancelUI(data))
#             return
#
#     await interaction.response.send_message("## You have no ongoing solving attempt!", ephemeral=True)


@tree.command(
    name="ping",
    description="Returns the bot's latency.",
    guild=discord.Object(id=CONST_GUILD_ID)
)
async def ping(interaction):
    embed = discord.Embed(title="Bot's ping", description=f'Ping/Latency is {round(client.latency * 1000)}ms!',
                          color=discord.Color.dark_red())
    await interaction.response.send_message(embed=embed)


@client.event
async def on_ready():
    await load()
    await tree.sync(guild=discord.Object(id=CONST_GUILD_ID))
    await client.change_presence(activity=discord.Game(name="I'm here!"), status=discord.Status.online)


client.run(token)
