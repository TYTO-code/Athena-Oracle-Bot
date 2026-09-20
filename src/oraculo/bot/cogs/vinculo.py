"""`/vincular-conta` e `/confirmar-vinculo` — RN-016 (RF-001, extensão).

Existem porque a importação do Firebase só liga `Membro.discord_id` quando o
documento já traz um `discordId` correto — quando a plataforma nunca
capturou isso, ninguém consegue ser encontrado pelo bot ao interagir pelo
Discord. Este fluxo deixa a própria pessoa provar que controla o e-mail
cadastrado na plataforma, sem depender de a plataforma já ter esse vínculo.

Deliberadamente **não** usa `bot.permissions.requer(...)`: aquele decorator
resolve o cargo do autor via `repo_membros.obter_ou_criar_por_discord`, que
criaria (e persistiria, já commitado) um `Membro` "zerado" para o `discord_id`
de qualquer pessoa que rodasse `/vincular-conta` — exatamente a situação que
`vinculo_service.confirmar_vinculo` existe para recusar (RN-016). Com
`@requer`, todo o fluxo cairia sempre em "peça a um Administrador", porque o
próprio primeiro comando plantaria o registro que o segundo depois rejeita
como duplicado. Mesmo princípio de RN-011 em `comunidade.py`, aplicado aqui à
etapa anterior a existir qualquer `Membro`.

Veja `services/vinculo_service.py` para os detalhes de segurança do desenho
(por que nunca revelamos se um identificador existe, por que o código nunca
fica em claro, por que cargo/XP não são tocados aqui).
"""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from oraculo.bot import embeds
from oraculo.db.base import sessao
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
    async def vincular_conta(self, interaction: discord.Interaction, identificador: str) -> None:
        await interaction.response.defer(ephemeral=True)
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
    async def confirmar_vinculo(self, interaction: discord.Interaction, codigo: str) -> None:
        await interaction.response.defer(ephemeral=True)
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
