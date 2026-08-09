"""Canal de notificação por e-mail (SMTP) — RF-010."""

from __future__ import annotations

from email.message import EmailMessage

from oraculo.config import Settings, get_settings
from oraculo.logging_config import get_logger
from oraculo.services.notificacao_service import Notificacao

log = get_logger(__name__)


class CanalEmail:
    """Envia a notificação por SMTP quando há destinatário e SMTP configurado."""

    nome = "email"

    def __init__(self, settings: Settings | None = None) -> None:
        self._cfg = settings or get_settings()

    async def enviar(self, notificacao: Notificacao) -> None:
        if not self._cfg.email_enabled or not notificacao.destinatario_email:
            return

        import aiosmtplib  # import tardio: só necessário quando há SMTP

        mensagem = EmailMessage()
        mensagem["From"] = self._cfg.smtp_from
        mensagem["To"] = notificacao.destinatario_email
        mensagem["Subject"] = notificacao.titulo
        detalhes = "\n".join(f"{k}: {v}" for k, v in notificacao.campos.items())
        mensagem.set_content(f"{notificacao.corpo}\n\n{detalhes}".strip())

        await aiosmtplib.send(
            mensagem,
            hostname=self._cfg.smtp_host,
            port=self._cfg.smtp_port,
            username=self._cfg.smtp_user,
            password=self._cfg.smtp_password,
            start_tls=self._cfg.smtp_port == 587,
        )
        log.info("E-mail enviado para %s: %s", notificacao.destinatario_email, notificacao.titulo)
