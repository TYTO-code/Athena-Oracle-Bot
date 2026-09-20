"""`/vincular-conta` e `/confirmar-vinculo` — RF-001 (extensão).

Existem porque a importação do Firebase só liga `Membro.discord_id` quando o
documento já traz um `discordId` correto — quando a plataforma nunca
capturou isso, ninguém consegue ser encontrado pelo bot ao interagir pelo
Discord. Este fluxo deixa a própria pessoa provar que controla o e-mail
cadastrado na plataforma, sem depender de a plataforma já ter esse vínculo.

Veja `services/vinculo_service.py` para os detalhes de segurança do desenho
(por que nunca revelamos se um identificador existe, por que o código nunca
fica em claro, por que cargo/XP não são tocados aqui).
"""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from oraculo.bot import embeds
from oraculo.bot.permissions import requer
from oraculo.db.base import sessao
from oraculo.domain.permissions import Acao
from oraculo.services import vinculo_service
from oraculo.services.notificacao_service import Notificacao, Severidade


class VinculoCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(
        name="vincular-conta",
        description="Liga sua conta Discord ao seu cadastro na plataforma do clube.",
    )
    @app_commands.describe(identificador="Seu e-mail ou ID cadastrado na plataforma do clube.")
    @requer(Acao.VINCULAR_CONTA, efemero=True)
    async def vincular_conta(self, interaction: discord.Interaction, identificador: str) -> None:
        if not self.bot.container.settings.email_enabled:
            await interaction.followup.send(
                embed=embeds.erro(
                    "O envio de e-mail não está configurado neste servidor — peça a um "
                    "Administrador para configurar o SMTP antes de usar este comando."
                ),
                ephemeral=True,
            )
            return

        async with sessao() as session:
            resultado = await vinculo_service.solicitar_vinculo(
                session, discord_id=interaction.user.id, identificador=identificador
            )

        if resultado.enviado and resultado.email_destino and resultado.codigo:
            await self.bot.container.notificacoes.enviar(
                Notificacao(
                    titulo="🔗 Código de vínculo — Bot Oráculo",
                    corpo=(
                        f"Seu código de verificação é **{resultado.codigo}**. "
                        "Expira em 10 minutos. Confirme com `/confirmar-vinculo` no Discord."
                    ),
                    severidade=Severidade.INFO,
                    destinatario_email=resultado.email_destino,
                )
            )

        # Mensagem sempre igual, exista ou não o identificador — não é feedback
        # de depuração, é uma barreira contra enumeração de e-mails/IDs alheios.
        await interaction.followup.send(
            embed=discord.Embed(
                title="📧 Verificação solicitada",
                description=(
                    "Se esse identificador existir na plataforma e ainda não estiver "
                    "vinculado a nenhuma conta, um código chegou por e-mail. Confirme com "
                    "`/confirmar-vinculo codigo:<código>` em até 10 minutos."
                ),
                color=discord.Color.blurple(),
            ),
            ephemeral=True,
        )

    @app_commands.command(
        name="confirmar-vinculo", description="Confirma o código de vínculo recebido por e-mail."
    )
    @app_commands.describe(codigo="O código de 6 dígitos recebido por e-mail.")
    @requer(Acao.VINCULAR_CONTA, efemero=True)
    async def confirmar_vinculo(self, interaction: discord.Interaction, codigo: str) -> None:
        async with sessao() as session:
            membro = await vinculo_service.confirmar_vinculo(
                session, discord_id=interaction.user.id, codigo=codigo
            )
            nome = membro.nome_exibicao

        await interaction.followup.send(
            embed=discord.Embed(
                title="✅ Conta vinculada",
                description=(
                    f"Sua conta do Discord agora está ligada ao cadastro de **{nome}** na "
                    "plataforma. O cargo e o XP acompanham a próxima sincronização."
                ),
                color=discord.Color.green(),
            ),
            ephemeral=True,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(VinculoCog(bot))
