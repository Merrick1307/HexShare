"""Email template loader using Jinja2.

Loads and renders email templates from app/templates/emails/.
Templates are organized by event type (nda, document) with .html and .txt variants.
"""
from __future__ import annotations

from pathlib import Path
from jinja2 import Environment, FileSystemLoader, TemplateNotFound

from app.ports.email_notification_port import EmailMessage


class EmailTemplateLoader:
    """Load and render email templates."""

    def __init__(self, *, brand_name: str = "HexShare"):
        base_dir = Path(__file__).resolve().parent.parent.parent
        templates_dir = base_dir / "templates" / "emails"
        self._brand_name = brand_name.strip() or "HexShare"

        if not templates_dir.exists():
            raise RuntimeError(f"Email templates directory not found: {templates_dir}")

        self.env = Environment(loader=FileSystemLoader(str(templates_dir)))

    def render_template(self, template_name: str, context: dict) -> str:
        """Render a template with given context.

        Parameters
        ----------
        template_name:
            Template name (e.g., "nda/created.html" or "document/shared.txt")
        context:
            Dictionary of variables for template rendering.

        Returns
        -------
        str
            Rendered template content.

        Raises
        ------
        TemplateNotFound
            If template does not exist.
        """
        try:
            template = self.env.get_template(template_name)
            rendered = template.render(**context)
            if self._brand_name != "HexShare":
                rendered = rendered.replace("HexShare", self._brand_name)
            return rendered
        except TemplateNotFound as e:
            raise TemplateNotFound(f"Email template not found: {template_name}") from e

    def create_email_message(
        self,
        to: str,
        subject: str,
        template_base: str,
        context: dict,
        cc: list = None,
        bcc: list = None,
        reply_to: str = None,
    ) -> EmailMessage:
        """Create an EmailMessage from templates.

        Parameters
        ----------
        to:
            Recipient email address.
        subject:
            Email subject line.
        template_base:
            Template base name without extension (e.g., "nda/created").
        context:
            Template variables.
        cc:
            CC recipients.
        bcc:
            BCC recipients.
        reply_to:
            Reply-To address.

        Returns
        -------
        EmailMessage
            Fully rendered email message.
        """
        # Render both text and HTML templates
        try:
            body = self.render_template(f"{template_base}.txt", context)
        except TemplateNotFound:
            body = ""

        try:
            html_body = self.render_template(f"{template_base}.html", context)
        except TemplateNotFound:
            html_body = None

        return EmailMessage(
            to=to,
            subject=subject,
            body=body or html_body or "",
            html_body=html_body,
            cc=cc,
            bcc=bcc,
            reply_to=reply_to,
        )
