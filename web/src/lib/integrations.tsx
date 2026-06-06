import type { ReactNode } from 'react';
import { ExternalLink } from 'lucide-react';
import type { IntegrationType } from '../api/endpoints';
import { CodeBlock, Step } from '../components/ui';

/** Form field descriptor for one secret/key on an integration. */
export interface IntegrationField {
  key: string;
  label: string;
  placeholder?: string;
  secret?: boolean;
}

/** Per-type metadata: which type label, which fields the form renders. */
export interface IntegrationTypeDef {
  value: IntegrationType;
  label: string;
  fields: IntegrationField[];
}

export const INTEGRATION_TYPES: IntegrationTypeDef[] = [
  {
    value: 'telegram',
    label: 'Telegram',
    fields: [
      { key: 'bot_token', label: 'Bot Token', placeholder: '123456789:ABC...', secret: true },
      { key: 'chat_id', label: 'Default Chat ID', placeholder: '-1001234567890' },
    ],
  },
  {
    value: 'slack',
    label: 'Slack',
    fields: [
      { key: 'webhook_url', label: 'Incoming Webhook URL', placeholder: 'https://hooks.slack.com/services/...' },
      { key: 'channel', label: 'Default Channel', placeholder: '#alerts' },
    ],
  },
  {
    value: 'webhook',
    label: 'Webhook',
    fields: [{ key: 'url', label: 'Webhook URL', placeholder: 'https://example.com/hook' }],
  },
  {
    value: 'email',
    label: 'Email (SMTP)',
    fields: [
      { key: 'smtp_host', label: 'SMTP Host' },
      { key: 'smtp_port', label: 'SMTP Port' },
      { key: 'from_email', label: 'From Address' },
      { key: 'default_recipients', label: 'Default Recipients (comma-separated)' },
    ],
  },
  {
    value: 'whatsapp',
    label: 'WhatsApp (Twilio)',
    fields: [
      { key: 'account_sid', label: 'Twilio Account SID', secret: true },
      { key: 'auth_token', label: 'Twilio Auth Token', secret: true },
      { key: 'from_number', label: 'From WhatsApp Number' },
    ],
  },
];

/** Inline link that opens t.me in a new tab with a small external-link glyph. */
export const TgLink = ({ to, children }: { to: string; children: ReactNode }) => (
  <a
    href={to}
    target="_blank"
    rel="noopener noreferrer"
    className="inline-flex items-center gap-1 text-cisco-blue hover:underline font-mono text-[12px]"
  >
    {children}
    <ExternalLink className="h-2.5 w-2.5" />
  </a>
);

/** Per-type, per-field hint content rendered inside a `?` popover. */
export const HINTS: Record<
  IntegrationType,
  Record<string, { title: string; body: ReactNode }>
> = {
  telegram: {
    bot_token: {
      title: 'Telegram bot token',
      body: (
        <div className="space-y-2">
          <p className="text-[13px] text-foreground/90">How to create a bot and get its token:</p>
          <ol className="space-y-1.5">
            <Step n={1}>
              Open Telegram, message <TgLink to="https://t.me/BotFather">@BotFather</TgLink>.
            </Step>
            <Step n={2}>
              Send <code className="font-mono text-[12px] bg-surface-subtle px-1 rounded-sm">/newbot</code>.
            </Step>
            <Step n={3}>
              Pick a display name and a username ending in <code className="font-mono text-[12px]">bot</code>{' '}
              (e.g. <code className="font-mono text-[12px]">netops_alert_bot</code>).
            </Step>
            <Step n={4}>
              BotFather replies with the HTTP API token. Paste it here.
            </Step>
          </ol>
          <p className="text-[12px] text-muted-foreground italic">
            Keep the token secret — anyone with it can send messages as your bot.
          </p>
        </div>
      ),
    },
    chat_id: {
      title: 'Telegram chat ID',
      body: (
        <div className="space-y-2.5">
          <p className="text-[13px] text-foreground/90">Three ways to find it:</p>
          <div>
            <p className="text-[12px] font-semibold text-foreground mb-1">1. Quick — ask a bot</p>
            <p className="text-[12px] text-foreground/90">
              Message <TgLink to="https://t.me/userinfobot">@userinfobot</TgLink> or{' '}
              <TgLink to="https://t.me/RawDataBot">@RawDataBot</TgLink>. Either replies with your
              numeric chat ID.
            </p>
          </div>
          <div>
            <p className="text-[12px] font-semibold text-foreground mb-1">2. Open a chat, then call</p>
            <p className="text-[12px] text-foreground/90 mb-1">
              Send{' '}
              <code className="font-mono text-[12px] bg-surface-subtle px-1 rounded-sm">/start</code>{' '}
              to your bot, then open:
            </p>
            <CodeBlock value="https://api.telegram.org/bot<TOKEN>/getUpdates" />
            <p className="text-[12px] text-foreground/90 mt-1">
              Copy <code className="font-mono text-[12px]">chat.id</code> from the JSON response.
            </p>
          </div>
          <div>
            <p className="text-[12px] font-semibold text-foreground mb-1">3. Group chat</p>
            <p className="text-[12px] text-foreground/90">
              Add the bot to the group, post a message, then call{' '}
              <code className="font-mono text-[12px]">getUpdates</code>. Group IDs are negative (e.g.{' '}
              <code className="font-mono text-[12px]">-1001234567890</code>).
            </p>
          </div>
        </div>
      ),
    },
  },
  slack: {
    webhook_url: {
      title: 'Slack incoming webhook',
      body: (
        <div className="space-y-2">
          <ol className="space-y-1.5">
            <Step n={1}>
              Open Slack, go to <code className="font-mono text-[12px]">api.slack.com/apps</code> and
              create an app (or pick an existing one).
            </Step>
            <Step n={2}>
              Sidebar → <strong>Incoming Webhooks</strong> → toggle ON →{' '}
              <strong>Add New Webhook to Workspace</strong>.
            </Step>
            <Step n={3}>
              Pick the default channel. Slack shows the URL — copy it and paste it here.
            </Step>
          </ol>
          <p className="text-[12px] text-muted-foreground italic">
            Per-rule channel overrides go in the alert rule config, not here.
          </p>
        </div>
      ),
    },
  },
  webhook: {
    url: {
      title: 'Webhook endpoint',
      body: (
        <div className="space-y-2">
          <p className="text-[13px] text-foreground/90">
            Any HTTPS endpoint that accepts POST with a JSON body.
          </p>
          <p className="text-[12px] text-foreground/90">NetOps sends:</p>
          <CodeBlock
            value={
              '{\n  "title": "Device Offline",\n  "message": "router-01 is now offline",\n  "severity": "critical",\n  "alert_type": "device_down"\n}'
            }
          />
          <p className="text-[12px] text-muted-foreground italic">
            Public URL with a valid cert. Self-signed won't work.
          </p>
        </div>
      ),
    },
  },
  email: {
    smtp_host: {
      title: 'SMTP host & port',
      body: (
        <div className="space-y-2">
          <p className="text-[12px] text-foreground/90">Common providers:</p>
          <ul className="text-[12px] font-mono space-y-0.5 text-foreground/90">
            <li>• Gmail: <code>smtp.gmail.com:587</code></li>
            <li>• Outlook/365: <code>smtp.office365.com:587</code></li>
            <li>• SendGrid: <code>smtp.sendgrid.net:587</code></li>
            <li>• Mailgun: <code>smtp.mailgun.org:587</code></li>
          </ul>
          <p className="text-[12px] text-muted-foreground italic">
            Port 587 + STARTTLS is standard.
          </p>
        </div>
      ),
    },
    from_email: {
      title: 'SMTP credentials',
      body: (
        <div className="space-y-2">
          <p className="text-[13px] text-foreground/90">
            Most providers require an <strong>app password</strong> — not your real account password.
          </p>
          <ul className="text-[12px] text-foreground/90 space-y-0.5">
            <li>• Gmail: myaccount.google.com → Security → 2FA on → App passwords</li>
            <li>• Outlook: account.microsoft.com → Security → App passwords</li>
          </ul>
          <p className="text-[12px] text-muted-foreground italic">
            The <code>from_email</code> must match the account that owns the app password.
          </p>
        </div>
      ),
    },
  },
  whatsapp: {
    account_sid: {
      title: 'Twilio credentials',
      body: (
        <div className="space-y-2">
          <ol className="space-y-1.5">
            <Step n={1}>
              Sign in at <TgLink to="https://console.twilio.com">console.twilio.com</TgLink>.
            </Step>
            <Step n={2}>Account SID and Auth Token sit at the top of the dashboard.</Step>
            <Step n={3}>
              For the <code>from_number</code>, use your Twilio WhatsApp-enabled sender (e.g.{' '}
              <code className="font-mono text-[12px]">+14155238886</code> for the sandbox).
            </Step>
          </ol>
          <p className="text-[12px] text-muted-foreground italic">
            Recipient numbers go in the alert rule config, not here.
          </p>
        </div>
      ),
    },
  },
};

/** Return the form-field list for a given integration type. */
export function getFieldsForType(t: IntegrationType): IntegrationField[] {
  return INTEGRATION_TYPES.find((x) => x.value === t)?.fields || [];
}

/** Return the friendly label for a given integration type. */
export function getTypeLabel(t: IntegrationType): string {
  return INTEGRATION_TYPES.find((x) => x.value === t)?.label || t;
}
