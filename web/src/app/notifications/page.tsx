"use client";

import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Bell, Check, ExternalLink, Loader2, Send, X } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { Card, CardHeader, CardTitle } from "@/components/ui/Card";
import { cn } from "@/lib/utils";

type Status = { discord_configured: boolean; slack_configured: boolean; any_configured: boolean };

export default function NotificationsPage() {
  const status = useQuery<Status>({
    queryKey: ["notify-status"],
    queryFn: () => api<Status>("/notify/status"),
  });

  return (
    <div className="px-4 py-6 md:px-8 md:py-8 max-w-5xl">
      <header className="mb-6">
        <div className="text-xs uppercase tracking-widest text-[var(--muted)]">Configuration</div>
        <h1 className="text-3xl font-semibold mt-1 inline-flex items-center gap-2">
          <Bell className="size-7" /> Notifications externes
        </h1>
        <p className="text-sm text-[var(--muted)] mt-2 max-w-2xl">
          Reçois automatiquement sur <b>Discord</b> ou <b>Slack</b> les événements importants du coach
          (rapport hebdo, nouvelle partie analysée, faiblesse à rejouer…) sans avoir à venir checker l&apos;app.
        </p>
      </header>

      <StatusBanner status={status.data} loading={status.isLoading} />

      <div className="grid lg:grid-cols-2 gap-4 mb-6">
        <SetupDiscord />
        <SetupSlack />
      </div>

      <EventsCard />
      <TestSection canSend={status.data?.any_configured ?? false} />
      <MessageFormatCard />
    </div>
  );
}

function StatusBanner({ status, loading }: { status?: Status; loading: boolean }) {
  return (
    <Card className={cn(
      "mb-6 border-l-4",
      status?.any_configured ? "border-l-[var(--accent)]" : "border-l-[var(--muted)]",
    )}>
      <div className="text-xs uppercase tracking-widest text-[var(--muted)] mb-2">État actuel</div>
      {loading && <div className="text-sm inline-flex items-center gap-2"><Loader2 className="size-4 animate-spin" /> Vérification…</div>}
      {status && (
        <div className="space-y-2">
          <StatusLine label="Discord" configured={status.discord_configured} envVar="DISCORD_WEBHOOK_URL" />
          <StatusLine label="Slack" configured={status.slack_configured} envVar="SLACK_WEBHOOK_URL" />
          {!status.any_configured && (
            <div className="text-xs text-[var(--muted)] italic mt-2">
              Aucun webhook configuré. Les guides ci-dessous expliquent comment en mettre un en place — c&apos;est gratuit et prend 2 minutes.
            </div>
          )}
        </div>
      )}
    </Card>
  );
}

function StatusLine({ label, configured, envVar }: { label: string; configured: boolean; envVar: string }) {
  return (
    <div className="flex items-center gap-3 text-sm">
      {configured
        ? <Check className="size-4 text-[var(--accent)] shrink-0" />
        : <X className="size-4 text-[var(--muted)] shrink-0" />
      }
      <span className="font-medium w-24">{label}</span>
      <span className={cn("text-xs", configured ? "text-[var(--accent)]" : "text-[var(--muted)]")}>
        {configured ? "Configuré et actif" : "Non configuré"}
      </span>
      <code className="text-[10px] font-mono text-[var(--muted)] ml-auto">{envVar}</code>
    </div>
  );
}

function SetupDiscord() {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Setup Discord</CardTitle>
        <a href="https://support.discord.com/hc/fr/articles/228383668" target="_blank" rel="noopener" className="text-xs text-[var(--info)] hover:underline inline-flex items-center gap-1">
          Doc officielle <ExternalLink className="size-3" />
        </a>
      </CardHeader>
      <ol className="text-sm space-y-3 list-decimal ml-5">
        <li>
          <b>Ouvre ton serveur Discord</b> où tu veux recevoir les notifs (perso ou un serveur partagé).
        </li>
        <li>
          <b>Crée ou choisis un salon</b> dédié (ex : <code className="font-mono text-xs">#coach-chess</code>) où les messages arriveront.
        </li>
        <li>
          <b>Clic droit sur le salon</b> → <i>Modifier le salon</i> → onglet <i>Intégrations</i> → <i>Créer un webhook</i>.
        </li>
        <li>
          <b>Nomme le webhook</b> (ex: « Coach Chess ») et clique <i>Copier l&apos;URL du webhook</i>.
        </li>
        <li>
          <b>Édite le <code className="font-mono text-xs">.env</code> du backend</b> et ajoute la ligne :
          <pre className="mt-2 bg-[var(--surface-2)] rounded px-2 py-1.5 text-[10px] font-mono overflow-x-auto whitespace-pre-wrap break-all">
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/123.../xyz...
          </pre>
        </li>
        <li>
          <b>Redémarre le backend</b> (<code className="font-mono text-xs">Ctrl+C</code> + relance), recharge cette page → l&apos;indicateur passe au vert.
        </li>
      </ol>
    </Card>
  );
}

function SetupSlack() {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Setup Slack</CardTitle>
        <a href="https://api.slack.com/messaging/webhooks" target="_blank" rel="noopener" className="text-xs text-[var(--info)] hover:underline inline-flex items-center gap-1">
          Doc officielle <ExternalLink className="size-3" />
        </a>
      </CardHeader>
      <ol className="text-sm space-y-3 list-decimal ml-5">
        <li>
          Va sur <a href="https://api.slack.com/apps" target="_blank" rel="noopener" className="text-[var(--info)] hover:underline">api.slack.com/apps</a> et <b>crée une nouvelle app</b> (« From scratch », nom : Coach Chess, workspace : ton choix).
        </li>
        <li>
          Dans l&apos;app, va dans <b>Incoming Webhooks</b> → active la fonction.
        </li>
        <li>
          Clique <b>Add New Webhook to Workspace</b> → choisis le canal de destination → Autorise.
        </li>
        <li>
          <b>Copie l&apos;URL du webhook</b> qui apparaît (format <code className="text-xs font-mono">https://hooks.slack.com/services/...</code>).
        </li>
        <li>
          <b>Édite le <code className="font-mono text-xs">.env</code> du backend</b> :
          <pre className="mt-2 bg-[var(--surface-2)] rounded px-2 py-1.5 text-[10px] font-mono overflow-x-auto whitespace-pre-wrap break-all">
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/T.../B.../...
          </pre>
        </li>
        <li>
          <b>Redémarre le backend</b>, recharge → indicateur vert.
        </li>
      </ol>
    </Card>
  );
}

function EventsCard() {
  const events = [
    { name: "Rapport hebdomadaire", when: "Chaque dimanche", desc: "Résumé semaine : parties jouées, Δ ELO, blunders, focus prochain. Issu de /weekly.", payload: "Titre + 4 fields (Parties, Δ ELO, Blunders, Focus)" },
    { name: "Nouvelle partie importée", when: "Auto, ~5min après que tu la termines sur chess.com", desc: "Le watcher chess.com détecte ta partie, l'analyse, et te notifie une fois le rapport prêt.", payload: "Titre + lien vers la review locale" },
    { name: "Ouverture maîtrisée", when: "Quand tu finis 7 jours d'affilée parfaits sur une ouverture", desc: "Le trainer te notifie de la victoire et de la prochaine ouverture sélectionnée.", payload: "Nom de l'ouverture + streak final" },
    { name: "Notifications manuelles", when: "Sur demande", desc: "Le bouton ci-dessous, ou n'importe quel script qui POST /notify/.", payload: "Libre" },
  ];
  return (
    <Card className="mb-4">
      <CardHeader><CardTitle>Événements qui déclenchent une notification</CardTitle></CardHeader>
      <table className="w-full text-sm">
        <thead className="text-xs text-[var(--muted)] uppercase tracking-wider">
          <tr className="border-b border-[var(--border)]">
            <th className="text-left py-2">Événement</th>
            <th className="text-left py-2">Quand</th>
            <th className="text-left py-2">Description</th>
            <th className="text-left py-2">Contenu</th>
          </tr>
        </thead>
        <tbody>
          {events.map((e, i) => (
            <tr key={i} className="border-b border-[var(--border)] last:border-0 align-top">
              <td className="py-2 font-medium">{e.name}</td>
              <td className="py-2 text-xs text-[var(--muted)]">{e.when}</td>
              <td className="py-2 text-xs">{e.desc}</td>
              <td className="py-2 text-xs text-[var(--muted)]">{e.payload}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </Card>
  );
}

function TestSection({ canSend }: { canSend: boolean }) {
  const [title, setTitle] = useState("Test depuis coach_chess");
  const [description, setDescription] = useState("Notification test pour vérifier que les webhooks Discord / Slack répondent.");

  const send = useMutation({
    mutationFn: () => api<{ ok: boolean; sent: { platform: string; status: number }[]; reason?: string }>(
      "/notify/", { json: { title, description } },
    ),
  });

  return (
    <Card className="mb-4">
      <CardHeader><CardTitle>Tester l&apos;envoi</CardTitle></CardHeader>
      <p className="text-xs text-[var(--muted)] mb-3">
        Envoie un message à tous les webhooks configurés. Utile après setup pour vérifier que tout est branché. Le message arrive en quelques secondes dans ton canal Discord/Slack.
      </p>
      {!canSend && (
        <div className="rounded border border-[var(--muted)]/30 bg-[var(--surface-2)] p-2 mb-3 text-xs text-[var(--muted)]">
          Aucun webhook configuré — l&apos;envoi va échouer. Configure d&apos;abord Discord ou Slack ci-dessus.
        </div>
      )}
      <div className="space-y-2 mb-3">
        <input
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="Titre"
          className="w-full bg-[var(--surface-2)] border rounded px-2 py-1.5 text-sm"
        />
        <textarea
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          placeholder="Description"
          rows={3}
          className="w-full bg-[var(--surface-2)] border rounded px-2 py-1.5 text-sm font-mono resize-y"
        />
      </div>
      <button
        onClick={() => send.mutate()}
        disabled={send.isPending || !canSend}
        className="text-xs px-4 py-2 rounded bg-[var(--accent)] text-black font-medium disabled:opacity-50 inline-flex items-center gap-1.5"
      >
        {send.isPending ? <Loader2 className="size-3 animate-spin" /> : <Send className="size-3" />}
        Envoyer le test
      </button>
      {send.isSuccess && (
        <div className="mt-3 rounded border border-[var(--accent)]/40 bg-[var(--accent)]/10 p-3 text-sm">
          <div className="text-[var(--accent)] font-medium">Envoyé</div>
          {send.data.sent.length > 0 && (
            <div className="text-xs text-[var(--muted)] mt-1">
              Destinations : {send.data.sent.map((s) => `${s.platform} (HTTP ${s.status})`).join(", ")}
            </div>
          )}
        </div>
      )}
      {send.isError && (
        <div className="mt-3 rounded border border-[var(--danger)]/40 bg-[var(--danger)]/10 p-3 text-xs text-[var(--danger)]">
          {send.error instanceof ApiError ? JSON.stringify(send.error.body) : String(send.error)}
        </div>
      )}
    </Card>
  );
}

function MessageFormatCard() {
  return (
    <Card>
      <CardHeader><CardTitle>À quoi ressemblent les messages</CardTitle></CardHeader>
      <div className="grid md:grid-cols-2 gap-4 text-xs">
        <div>
          <div className="text-xs uppercase tracking-widest text-[var(--muted)] mb-2">Discord (embed)</div>
          <div className="rounded border-l-4 border-l-[var(--accent)] bg-[var(--surface-2)] p-3">
            <div className="font-bold text-sm mb-1 text-[var(--foreground)]">Coach hebdo — semaine 2026-06-22</div>
            <div className="text-[var(--muted)] mb-2">Tu as joué 8 parties cette semaine avec un Δ ELO de +12. Trois blunders détectés, tous en endgame. La semaine prochaine, focus sur les finales de tour.</div>
            <div className="grid grid-cols-2 gap-x-3 gap-y-1 tabular-nums">
              <div><b>Parties</b> 8</div>
              <div><b>Δ ELO</b> +12</div>
              <div><b>Blunders</b> 3</div>
              <div><b>Focus</b> endgame</div>
            </div>
            <div className="text-[10px] text-[var(--muted)] mt-2">coach_chess</div>
          </div>
        </div>
        <div>
          <div className="text-xs uppercase tracking-widest text-[var(--muted)] mb-2">Slack (block kit)</div>
          <div className="rounded border bg-[var(--surface-2)] p-3">
            <div className="font-bold text-sm mb-1">Coach hebdo — semaine 2026-06-22</div>
            <div className="text-[var(--muted)] mb-2">Tu as joué 8 parties cette semaine avec un Δ ELO de +12...</div>
            <div className="space-y-0.5 font-mono tabular-nums">
              <div>Parties: 8</div>
              <div>Δ ELO: +12</div>
              <div>Blunders: 3</div>
              <div>Focus: endgame</div>
            </div>
          </div>
        </div>
      </div>
    </Card>
  );
}
