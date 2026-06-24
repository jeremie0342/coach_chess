"use client";

import { Card, CardHeader, CardTitle } from "@/components/ui/Card";
import { JobButton } from "@/components/admin/JobButton";
import { ImportMonthForm } from "@/components/admin/ImportMonthForm";
import { useIdentity } from "@/hooks/useIdentity";

export default function AdminPage() {
  const me = useIdentity();
  return (
    <div className="px-4 py-6 md:px-8 md:py-8 max-w-5xl">
      <header className="mb-6">
        <div className="text-xs uppercase tracking-widest text-[var(--muted)]">Outils</div>
        <h1 className="text-3xl font-semibold mt-1">Admin / Pipeline</h1>
        <p className="text-sm text-[var(--muted)] mt-2">
          Toutes les actions longues du backend, exécutées en arrière-plan par le worker arq.
        </p>
      </header>

      <div className="space-y-4">
        <Card>
          <CardHeader><CardTitle>Import</CardTitle></CardHeader>
          <JobButton
            label="Importer toutes les parties chess.com"
            description={`Tire l'historique complet de ${me.chesscom_username} et persiste en base.`}
            path="/async/import/chesscom/full"
          />
          {me.lichess_username && (
            <JobButton
              label="Importer les parties Lichess récentes"
              description={`Tire les 100 dernières parties Lichess de ${me.lichess_username}. Idempotent (skip celles déjà connues).`}
              path="/async/import/lichess"
              body={{ max_games: 100 }}
            />
          )}
          <JobButton
            label="Watch — tick manuel"
            description="Force un cycle du watcher (import nouvelles parties + analyse + puzzles + faiblesses)."
            path="/async/coach/watch"
            body={{ depth: 14 }}
          />
          <ImportMonthForm />
        </Card>

        <Card>
          <CardHeader><CardTitle>Analyse Stockfish</CardTitle></CardHeader>
          <JobButton
            label="Analyser les parties en attente"
            description="Limite 100, profondeur par défaut."
            path="/async/analyze/pending"
            body={{ limit: 100 }}
          />
          <JobButton
            label="Re-analyse profonde des positions critiques"
            description="Profondeur 28 sur les blunders ≥150cp (limite 50)."
            path="/async/analyze/deep/critical"
            body={{ limit: 50, depth: 28, min_cp_loss: 150, force: false }}
          />
        </Card>

        <Card>
          <CardHeader><CardTitle>Détection & génération</CardTitle></CardHeader>
          <JobButton
            label="Rafraîchir les faiblesses"
            description="Refait tourner les 10+ détecteurs sur toutes mes parties."
            path="/async/player/me/weaknesses/refresh"
          />
          <JobButton
            label="Générer des puzzles depuis mes blunders"
            description="Min 120 cp loss."
            path="/async/exercises/generate"
            body={{ min_cp_loss: 120 }}
          />
        </Card>

        <Card>
          <CardHeader><CardTitle>Répertoire</CardTitle></CardHeader>
          <JobButton
            label="Reconstruire le répertoire empirique"
            description="Reconstruit l'arbre des coups joués depuis 0."
            path="/async/repertoire/me/rebuild"
          />
        </Card>

        <Card>
          <CardHeader><CardTitle>Progression</CardTitle></CardHeader>
          <JobButton
            label="Snapshot des métriques (async)"
            description="Variante async du snapshot — équivalent au bouton sur /progress mais via le worker."
            path="/async/coach/me/progress/snapshot"
          />
        </Card>
      </div>
    </div>
  );
}
