import discord
from threading import Thread
import time
from discord.ext import commands
import asyncio
import os
from dotenv import load_dotenv
from datetime import datetime
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
        title=f"PT {pt_id} - {'[ENCERRADA]' if pt['fechada'] else 'Escolha sua Função'}",
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
        embed.add_field(name=f"{close_emoji} Encerrar PT", value="Apenas o criador da PT ou ADM pode encerrar", inline=False)

    return embed

async def auto_close_pt(pt_id, delay=300): 
    """Encerra automaticamente a PT se não houver reações após o tempo especificado"""
    await asyncio.sleep(delay)
    
    if pt_id in parties and not parties[pt_id]["fechada"]:
        pt = parties[pt_id]
        total_membros = len(pt["Líder"]) + len(pt["Healer"]) + len(pt["Membro"])
        
        if total_membros == 0:  
            pt["fechada"] = True
            embed = gerar_embed(pt_id, pt["msg"].guild)
            embed.add_field(name="⏰ Auto-encerramento", value="PT encerrada automaticamente por inatividade (5 min)", inline=False)
            await pt["msg"].edit(embed=embed)
            
            await pt["msg"].channel.send(f"⏰ PT {pt_id} foi encerrada automaticamente por inatividade (5 minutos sem participantes).")

def remover_usuario_de_todas_funcoes(pt_data, user_id):
    """Remove o usuário de todas as funções da PT"""
    for funcao in ["Líder", "Healer", "Membro"]:
        if user_id in pt_data[funcao]:
            pt_data[funcao].remove(user_id)
            return funcao
    return None

def user_pode_fechar_pt(user, guild, pt_data):
    """Verifica se o usuário pode encerrar a PT (criador ou admin)"""
    if user.id == pt_data.get("criador_id"):
        return True
    
    member = guild.get_member(user.id)
    if member and member.guild_permissions.administrator:
        return True
    
    return False

async def delete_command_message(ctx, delay=3):
    """Deleta a mensagem de comando após um delay"""
    try:
        await asyncio.sleep(delay)
        await ctx.message.delete()
    except discord.NotFound:
        pass  # Mensagem já foi deletada
    except discord.Forbidden:
        pass  # Bot não tem permissão para deletar mensagens

async def delete_message_after_delay(message, delay):
    """Deleta uma mensagem após um delay"""
    try:
        await asyncio.sleep(delay)
        await message.delete()
    except (discord.NotFound, discord.Forbidden):
        pass

def keep_alive():
    """Servidor HTTP para manter o bot ativo no Render"""
    from http.server import HTTPServer, BaseHTTPRequestHandler
    import json
    
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            
            status = {
                "status": "online",
                "bot_name": str(bot.user) if bot.user else "Bot não conectado",
                "uptime": datetime.now().isoformat(),
                "guilds": len(bot.guilds) if bot.guilds else 0,
                "parties_active": len([pt for pt in parties.values() if not pt["fechada"]]),
                "total_parties": len(parties)
            }
            
            self.wfile.write(json.dumps(status, indent=2).encode())
        
        def log_message(self, format, *args):
            # Silencia logs do servidor HTTP para não poluir console
            pass
    
    server = HTTPServer(('0.0.0.0', 8000), Handler)
    server.serve_forever()

async def self_ping():
    """Faz ping no próprio serviço para evitar que durma (apenas em produção)"""
    try:
        import aiohttp
    except ImportError:
        print("⚠️ aiohttp não instalado - self-ping desabilitado")
        return
    
    # Só ativa o self-ping se estiver no Render
    if not os.getenv('RENDER'):
        print("ℹ️ Self-ping desabilitado (não está no Render)")
        return
        
    render_url = os.getenv('RENDER_EXTERNAL_URL')
    if not render_url:
        print("⚠️ RENDER_EXTERNAL_URL não configurada - self-ping desabilitado")
        return
    
    print(f"✅ Self-ping ativado: {render_url}")
    
    while True:
        try:
            # Aguarda 14 minutos (antes dos 15 min de timeout do Render)
            await asyncio.sleep(14 * 60)  # 14 minutos
            
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
                async with session.get(render_url) as response:
                    if response.status == 200:
                        print(f"✅ Self-ping realizado: {datetime.now().strftime('%H:%M:%S')}")
                    else:
                        print(f"⚠️ Self-ping falhou: {response.status}")
                        
        except Exception as e:
            print(f"❌ Erro no self-ping: {e}")
            # Continua tentando mesmo com erro
            await asyncio.sleep(60)  # Aguarda 1 minuto antes de tentar novamente

def is_pt_message(message_id):
    """Verifica se uma mensagem é de uma PT (original ou de listagem)"""
    for pt_id, pt_data in parties.items():
        # Verifica se é a mensagem original da PT
        if pt_data["msg"] and message_id == pt_data["msg"].id:
            return pt_id, pt_data, "original"
        
        # Verifica se é uma mensagem de listagem
        for lista_msg in pt_data["lista_msgs"]:
            if message_id == lista_msg.id:
                return pt_id, pt_data, "lista"
    
    return None, None, None

@bot.event
async def on_ready():
    print(f'✅ Bot conectado como {bot.user}')
    print(f'Bot está em {len(bot.guilds)} servidor(es)')
    
    # Inicia o self-ping após bot estar pronto
    await asyncio.sleep(30)  # Aguarda 30 segundos para estabilizar
    asyncio.create_task(self_ping())

@bot.command()
async def criar_pt(ctx):
    pt_id = len(parties) + 1
    parties[pt_id] = {
        "Líder": [], 
        "Healer": [], 
        "Membro": [], 
        "msg": None, 
        "fechada": False,
        "criador_id": ctx.author.id,
        "lista_msgs": []  # Para armazenar mensagens do !listar_pts
    }

    embed = gerar_embed(pt_id, ctx.guild)
    msg = await ctx.send(embed=embed)

    for emoji in valid_emojis:
        await msg.add_reaction(emoji)
    await msg.add_reaction(close_emoji)  

    parties[pt_id]["msg"] = msg
    confirmation_msg = await ctx.send(f"✅ PT {pt_id} criada por {ctx.author.mention}! Reaja para entrar.")
    
    # Deleta o comando e a mensagem de confirmação após alguns segundos
    asyncio.create_task(delete_command_message(ctx))
    asyncio.create_task(delete_message_after_delay(confirmation_msg, 10))
    
    asyncio.create_task(auto_close_pt(pt_id))

@bot.command()
async def listar_pts(ctx):
    if not parties:
        error_msg = await ctx.send("❌ Nenhuma PT foi criada ainda.")
        asyncio.create_task(delete_command_message(ctx))
        asyncio.create_task(delete_message_after_delay(error_msg, 10))
        return

    # Remove mensagens anteriores de listagem desta PT
    for pt_id in parties:
        pt = parties[pt_id]
        for old_msg in pt["lista_msgs"]:
            try:
                await old_msg.delete()
            except (discord.NotFound, discord.Forbidden):
                pass
        pt["lista_msgs"].clear()

    for pt_id in parties:
        embed = gerar_embed(pt_id, ctx.guild)
        msg = await ctx.send(embed=embed)
        
        # Adiciona reações apenas se a PT não estiver encerrada
        if not parties[pt_id]["fechada"]:
            for emoji in valid_emojis:
                await msg.add_reaction(emoji)
            await msg.add_reaction(close_emoji)
        
        # Armazena a mensagem para poder deletá-la depois
        parties[pt_id]["lista_msgs"].append(msg)
    
    # Deleta o comando
    asyncio.create_task(delete_command_message(ctx))

@bot.command()
async def remover_jogador(ctx, pt_id: int, membro: discord.Member):
    if pt_id not in parties:
        error_msg = await ctx.send("❌ Esta PT não existe.")
        asyncio.create_task(delete_command_message(ctx))
        asyncio.create_task(delete_message_after_delay(error_msg, 10))
        return

    pt = parties[pt_id]
    funcao_removida = remover_usuario_de_todas_funcoes(pt, membro.id)

    if not funcao_removida:
        error_msg = await ctx.send(f"❌ {membro.mention} não está na PT {pt_id}.")
        asyncio.create_task(delete_command_message(ctx))
        asyncio.create_task(delete_message_after_delay(error_msg, 10))
        return

    embed = gerar_embed(pt_id, ctx.guild)
    await pt["msg"].edit(embed=embed)
    
    # Atualiza também as mensagens de listagem
    for lista_msg in pt["lista_msgs"]:
        try:
            await lista_msg.edit(embed=embed)
        except (discord.NotFound, discord.Forbidden):
            pass
    
    success_msg = await ctx.send(f"✅ {membro.mention} foi removido da função {funcao_removida} na PT {pt_id}!")
    asyncio.create_task(delete_command_message(ctx))
    asyncio.create_task(delete_message_after_delay(success_msg, 10))

@bot.command()
async def comandos(ctx):
    embed = discord.Embed(
        title="📜 Lista de Comandos",
        description="Aqui estão os comandos disponíveis para gerenciar as PTs:",
        color=discord.Color.green()
    )
    embed.add_field(name="!criar_pt", value="Cria uma nova PT.", inline=False)
    embed.add_field(name="!listar_pts", value="Lista todas as PTs criadas e seus membros (com reações funcionais).", inline=False)
    embed.add_field(name="!remover_jogador <id> @usuário", value="Remove um jogador da PT informada.", inline=False)
    embed.add_field(name="!comandos", value="Mostra esta lista de comandos.", inline=False)
    
    embed.add_field(name="ℹ️ Como usar:", value="• Reaja com 🛡️ para ser Líder\n• Reaja com ⚕️ para ser Healer\n• Reaja com ⚔️ para ser Membro\n• Reaja com ❌ para encerrar PT (criador/ADM)", inline=False)
    embed.add_field(name="📋 Regras:", value="• Máximo 1 Líder e 1 Healer\n• Máximo 6 Membros\n• Total máximo de 8 jogadores\n• Cada pessoa pode ter apenas 1 função\n• PT encerra automaticamente em 5min se vazia", inline=False)
    embed.add_field(name="🔧 Recursos:", value="• Comandos são automaticamente removidos\n• !listar_pts mostra PTs com reações funcionais\n• Mensagens de confirmação são removidas automaticamente", inline=False)

    msg = await ctx.send(embed=embed)
    asyncio.create_task(delete_command_message(ctx))

@bot.event
async def on_reaction_add(reaction, user):
    if user.bot:
        return
    if reaction.message.author != bot.user:
        return

    pt_id, pt_data, msg_type = is_pt_message(reaction.message.id)
    
    if not pt_data:
        return

    if str(reaction.emoji) == close_emoji:
        if pt_data["fechada"]:
            await reaction.remove(user)
            return
            
        if user_pode_fechar_pt(user, reaction.message.guild, pt_data):
            pt_data["fechada"] = True
            embed = gerar_embed(pt_id, reaction.message.guild)
            
            # Atualiza a mensagem original
            await pt_data["msg"].edit(embed=embed)
            
            # Atualiza todas as mensagens de listagem e remove reações
            for lista_msg in pt_data["lista_msgs"]:
                try:
                    await lista_msg.edit(embed=embed)
                    await lista_msg.clear_reactions()
                except (discord.NotFound, discord.Forbidden):
                    pass
            
            criador = reaction.message.guild.get_member(pt_data["criador_id"])
            criador_nome = criador.display_name if criador else "Desconhecido"
            
            encerramento_msg = await reaction.message.channel.send(f"🚫 PT {pt_id} foi encerrada por {user.mention}! (Criada por {criador_nome})")
            asyncio.create_task(delete_message_after_delay(encerramento_msg, 15))
        else:
            await reaction.remove(user)
            try:
                await user.send(f"❌ Apenas o criador da PT {pt_id} ou um administrador pode encerrá-la.")
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

    # Remove reações de outras funções apenas na mensagem atual
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
    
    # Atualiza a mensagem original
    await pt_data["msg"].edit(embed=new_embed)
    
    # Atualiza todas as mensagens de listagem
    for lista_msg in pt_data["lista_msgs"]:
        try:
            await lista_msg.edit(embed=new_embed)
        except (discord.NotFound, discord.Forbidden):
            pass

@bot.event
async def on_reaction_remove(reaction, user):
    if user.bot:
        return
    if reaction.message.author != bot.user:
        return

    pt_id, pt_data, msg_type = is_pt_message(reaction.message.id)
    
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
        
        # Atualiza a mensagem original
        await pt_data["msg"].edit(embed=new_embed)
        
        # Atualiza todas as mensagens de listagem
        for lista_msg in pt_data["lista_msgs"]:
            try:
                await lista_msg.edit(embed=new_embed)
            except (discord.NotFound, discord.Forbidden):
                pass

# Inicia servidor HTTP em thread separada
Thread(target=keep_alive, daemon=True).start()

bot.run(os.getenv('DISCORD_TOKEN'))
