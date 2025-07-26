import discord
from threading import Thread
import time
from discord.ext import commands
import asyncio
import os
from dotenv import load_dotenv
load_dotenv()

intents = discord.Intents.default()
intents.reactions = True
intents.messages = True
intents.guilds = True
intents.members = True
intents.message_content = True  
bot = commands.Bot(command_prefix="!", intents=intents)

parties = {}
valid_emojis = {"🛡️": "Líder", "⚕️": "Healer", "⚔️": "Membro"}
close_emoji = "❌"

def get_display_name(guild, user_id):
    member = guild.get_member(user_id)
    return member.display_name if member else f"Usuário ({user_id})"

def gerar_embed(pt_id, guild):
    pt = parties[pt_id]
    embed = discord.Embed(
        title=f"PT {pt_id} - {'[FECHADA]' if pt['fechada'] else 'Escolha sua Função'}",
        description="Reaja com um dos emojis abaixo para entrar na PT." if not pt["fechada"] else "🚫 Esta PT foi encerrada.",
        color=discord.Color.red() if pt["fechada"] else discord.Color.blue()
    )

    for emoji, role in valid_emojis.items():
        membros = pt[role]
        nomes = "\n".join(get_display_name(guild, uid) for uid in membros) or "Nenhum"
        limite = 1 if role != "Membro" else 6
        embed.add_field(name=f"{emoji} {role} ({len(membros)}/{limite})", value=nomes, inline=False)

    total = len(pt["Líder"]) + len(pt["Healer"]) + len(pt["Membro"])
    embed.set_footer(text=f"Total: {total}/8 jogadores")
    
    if not pt["fechada"]:
        embed.add_field(name=f"{close_emoji} Fechar PT", value="Apenas o criador da PT ou ADM pode fechar", inline=False)

    return embed

async def auto_close_pt(pt_id, delay=300): 
    """Fecha automaticamente a PT se não houver reações após o tempo especificado"""
    await asyncio.sleep(delay)
    
    if pt_id in parties and not parties[pt_id]["fechada"]:
        pt = parties[pt_id]
        total_membros = len(pt["Líder"]) + len(pt["Healer"]) + len(pt["Membro"])
        
        if total_membros == 0:  
            pt["fechada"] = True
            embed = gerar_embed(pt_id, pt["msg"].guild)
            embed.add_field(name="⏰ Auto-fechamento", value="PT fechada automaticamente por inatividade (5 min)", inline=False)
            await pt["msg"].edit(embed=embed)
            
            await pt["msg"].channel.send(f"⏰ PT {pt_id} foi fechada automaticamente por inatividade (5 minutos sem participantes).")

def remover_usuario_de_todas_funcoes(pt_data, user_id):
    """Remove o usuário de todas as funções da PT"""
    for funcao in ["Líder", "Healer", "Membro"]:
        if user_id in pt_data[funcao]:
            pt_data[funcao].remove(user_id)
            return funcao
    return None

def user_pode_fechar_pt(user, guild, pt_data):
    """Verifica se o usuário pode fechar a PT (criador ou admin)"""
    if user.id == pt_data.get("criador_id"):
        return True
    
    member = guild.get_member(user.id)
    if member and member.guild_permissions.administrator:
        return True
    
    return False

@bot.event
async def on_ready():
    print(f'✅ Bot conectado como {bot.user}')
    print(f'Bot está em {len(bot.guilds)} servidor(es)')

@bot.command()
async def criar_pt(ctx):
    pt_id = len(parties) + 1
    parties[pt_id] = {
        "Líder": [], 
        "Healer": [], 
        "Membro": [], 
        "msg": None, 
        "fechada": False,
        "criador_id": ctx.author.id  
    }

    embed = gerar_embed(pt_id, ctx.guild)
    msg = await ctx.send(embed=embed)

    for emoji in valid_emojis:
        await msg.add_reaction(emoji)
    await msg.add_reaction(close_emoji)  

    parties[pt_id]["msg"] = msg
    await ctx.send(f"✅ PT {pt_id} criada por {ctx.author.mention}! Reaja para entrar.")
    
    asyncio.create_task(auto_close_pt(pt_id))

@bot.command()
async def listar_pts(ctx):
    if not parties:
        await ctx.send("❌ Nenhuma PT foi criada ainda.")
        return

    for pt_id in parties:
        embed = gerar_embed(pt_id, ctx.guild)
        await ctx.send(embed=embed)

@bot.command()
async def remover_jogador(ctx, pt_id: int, membro: discord.Member):
    if pt_id not in parties:
        await ctx.send("❌ Esta PT não existe.")
        return

    pt = parties[pt_id]
    funcao_removida = remover_usuario_de_todas_funcoes(pt, membro.id)

    if not funcao_removida:
        await ctx.send(f"❌ {membro.mention} não está na PT {pt_id}.")
        return

    embed = gerar_embed(pt_id, ctx.guild)
    await pt["msg"].edit(embed=embed)
    await ctx.send(f"✅ {membro.mention} foi removido da função {funcao_removida} na PT {pt_id}!")

@bot.command()
async def comandos(ctx):
    embed = discord.Embed(
        title="📜 Lista de Comandos",
        description="Aqui estão os comandos disponíveis para gerenciar as PTs:",
        color=discord.Color.green()
    )
    embed.add_field(name="!criar_pt", value="Cria uma nova PT.", inline=False)
    embed.add_field(name="!listar_pts", value="Lista todas as PTs criadas e seus membros.", inline=False)
    embed.add_field(name="!remover_jogador <id> @usuário", value="Remove um jogador da PT informada.", inline=False)
    embed.add_field(name="!comandos", value="Mostra esta lista de comandos.", inline=False)
    
    embed.add_field(name="ℹ️ Como usar:", value="• Reaja com 🛡️ para ser Líder\n• Reaja com ⚕️ para ser Healer\n• Reaja com ⚔️ para ser Membro\n• Reaja com ❌ para fechar PT (criador/ADM)", inline=False)
    embed.add_field(name="📋 Regras:", value="• Máximo 1 Líder e 1 Healer\n• Máximo 6 Membros\n• Total máximo de 8 jogadores\n• Cada pessoa pode ter apenas 1 função\n• PT fecha automaticamente em 5min se vazia", inline=False)

    await ctx.send(embed=embed)

@bot.event
async def on_reaction_add(reaction, user):
    if user.bot:
        return
    if reaction.message.author != bot.user:
        return

    pt_id = None
    pt_data = None
    for id_pt, data in parties.items():
        if data["msg"] and reaction.message.id == data["msg"].id:
            pt_id = id_pt
            pt_data = data
            break
    
    if not pt_data:
        return

    if str(reaction.emoji) == close_emoji:
        if pt_data["fechada"]:
            await reaction.remove(user)
            return
            
        if user_pode_fechar_pt(user, reaction.message.guild, pt_data):
            pt_data["fechada"] = True
            embed = gerar_embed(pt_id, reaction.message.guild)
            await pt_data["msg"].edit(embed=embed)
            
            criador = reaction.message.guild.get_member(pt_data["criador_id"])
            criador_nome = criador.display_name if criador else "Desconhecido"
            
            await reaction.message.channel.send(f"🚫 PT {pt_id} foi fechada por {user.mention}! (Criada por {criador_nome})")
        else:
            await reaction.remove(user)
            try:
                await user.send(f"❌ Apenas o criador da PT {pt_id} ou um administrador pode fechá-la.")
            except:
                pass
        return

    if reaction.emoji not in valid_emojis:
        await reaction.remove(user)
        return

    if pt_data["fechada"]:
        await reaction.remove(user)
        try:
            await user.send(f"❌ A PT {pt_id} já foi encerrada.")
        except:
            pass  
        return

    funcao_atual = None
    for funcao in ["Líder", "Healer", "Membro"]:
        if user.id in pt_data[funcao]:
            funcao_atual = funcao
            break

    nova_funcao = valid_emojis[reaction.emoji]
    
    
    if funcao_atual == nova_funcao:
        return

    
    maximo = 1 if nova_funcao != "Membro" else 6
    if len(pt_data[nova_funcao]) >= maximo:
        await reaction.remove(user)
        try:
            await user.send(f"❌ A função {nova_funcao} já está cheia na PT {pt_id}.")
        except:
            pass
        return

    
    if not funcao_atual:
        total = len(pt_data["Líder"]) + len(pt_data["Healer"]) + len(pt_data["Membro"])
        if total >= 8:
            await reaction.remove(user)
            try:
                await user.send(f"❌ A PT {pt_id} já está cheia (8/8 jogadores).")
            except:
                pass
            return

    
    if funcao_atual:
        pt_data[funcao_atual].remove(user.id)

    
    pt_data[nova_funcao].append(user.id)

    
    try:
        for emoji in valid_emojis:
            if emoji != reaction.emoji:
                await reaction.message.remove_reaction(emoji, user)
    except:
        pass  

    
    try:
        if funcao_atual:
            await user.send(f"✅ Você mudou de {funcao_atual} para {nova_funcao} na PT {pt_id}!")
        else:
            await user.send(f"✅ Você agora é {nova_funcao} na PT {pt_id}!")
    except:
        pass  

    new_embed = gerar_embed(pt_id, reaction.message.guild)
    await pt_data["msg"].edit(embed=new_embed)

@bot.event
async def on_reaction_remove(reaction, user):
    if user.bot:
        return
    if reaction.message.author != bot.user:
        return

    pt_id = None
    pt_data = None
    for id_pt, data in parties.items():
        if data["msg"] and reaction.message.id == data["msg"].id:
            pt_id = id_pt
            pt_data = data
            break
    
    if not pt_data or pt_data["fechada"]:
        return

    if reaction.emoji not in valid_emojis:
        return

    funcao = valid_emojis[reaction.emoji]
    if user.id in pt_data[funcao]:
        pt_data[funcao].remove(user.id)
        
        try:
            await user.send(f"❌ Você saiu da função {funcao} na PT {pt_id}.")
        except:
            pass

        new_embed = gerar_embed(pt_id, reaction.message.guild)
        await pt_data["msg"].edit(embed=new_embed)

def keep_alive():
    from http.server import HTTPServer, BaseHTTPRequestHandler
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"Bot is running!")
    
    server = HTTPServer(('0.0.0.0', 8000), Handler)
    server.serve_forever()

Thread(target=keep_alive, daemon=True).start()

bot.run(os.getenv('DISCORD_TOKEN'))