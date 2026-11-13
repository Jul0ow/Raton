# syntax=docker/dockerfile:1
#
# Image d'outillage de Raton : outils de contrôle aux versions épinglées, scripts et règles.
#
# Construite par l'équipe infra et poussée dans JFrog ; le pipeline l'utilise par digest
# (variable RATON_IMAGE). Contexte de construction : la racine du dépôt Raton.
#
#   docker build -f ci/Dockerfile \
#     --build-arg MIROIR_GITHUB=https://jfrog.example.com/artifactory/github \
#     --build-arg PIP_INDEX_URL=https://jfrog.example.com/artifactory/api/pypi/pypi/simple \
#     -t jfrog.example.com/raton/outillage:<version> .
#
# Tout téléchargement passe par JFrog et se vérifie par une somme SHA-256 écrite ici.
# Mettre à jour un outil : docs/controles.md, « Mettre à jour un outil ».

ARG IMAGE_PYTHON=python:3.13-slim-trixie@sha256:e48f59cdba69a3cbd9ed2cf0f348d90d45a8d350d98134cf1070bc106ee9ed90

# --- Outils : archives téléchargées, sommes vérifiées, seul l'exécutable gardé ---------
FROM ${IMAGE_PYTHON} AS outils
ARG TARGETARCH
ARG MIROIR_GITHUB=https://github.com

# gitleaks 8.30.1, publié le 2026-02-21 : secrets dans l'arbre et l'historique git.
ARG GITLEAKS_VERSION=8.30.1
ARG GITLEAKS_SHA256_AMD64=551f6fc83ea457d62a0d98237cbad105af8d557003051f41f3e7ca7b3f2470eb
ARG GITLEAKS_SHA256_ARM64=e4a487ee7ccd7d3a7f7ec08657610aa3606637dab924210b3aee62570fb4b080

# Trivy 0.76.1, publié le 2026-10-21 : base de vulnérabilités (phase de préparation) ;
# CVE, licences, SBOM et configuration du déploiement avec les contrôles suivants.
ARG TRIVY_VERSION=0.76.1
ARG TRIVY_SHA256_AMD64=c7cbe3137fb8a48a17574bede3dd6beb16742d1e9772929940fc90082c39d9c0
ARG TRIVY_SHA256_ARM64=e174dff2a6dba5e3ae41f8d0537a6324405bd08132497340304c6b20e0f16a1f

COPY ci/telecharger.py /tmp/telecharger.py
RUN set -eu; \
    case "${TARGETARCH:-amd64}" in \
      amd64) g=x64;   t=64bit; gs="$GITLEAKS_SHA256_AMD64"; ts="$TRIVY_SHA256_AMD64" ;; \
      arm64) g=arm64; t=ARM64; gs="$GITLEAKS_SHA256_ARM64"; ts="$TRIVY_SHA256_ARM64" ;; \
      *) echo "architecture non prise en charge : $TARGETARCH" >&2; exit 1 ;; \
    esac; \
    mkdir -p /opt/raton/bin; \
    python3 -I /tmp/telecharger.py \
      "$MIROIR_GITHUB/gitleaks/gitleaks/releases/download/v$GITLEAKS_VERSION/gitleaks_${GITLEAKS_VERSION}_linux_$g.tar.gz" \
      "$gs" gitleaks /opt/raton/bin/gitleaks; \
    python3 -I /tmp/telecharger.py \
      "$MIROIR_GITHUB/aquasecurity/trivy/releases/download/v$TRIVY_VERSION/trivy_${TRIVY_VERSION}_Linux-$t.tar.gz" \
      "$ts" trivy /opt/raton/bin/trivy

# --- Image finale --------------------------------------------------------------------
FROM ${IMAGE_PYTHON}
ARG PIP_INDEX_URL=https://pypi.org/simple

# git : clone du dépôt relu et lecture de son historique. Rien d'autre du système.
# apt passe par le miroir Debian de JFrog si l'équipe infra le configure ici.
RUN apt-get update \
 && apt-get install -y --no-install-recommends git ca-certificates \
 && rm -rf /var/lib/apt/lists/*

# Si JFrog présente un certificat signé par une autorité interne, l'ajouter ici :
#   COPY ac-interne.crt /usr/local/share/ca-certificates/
#   RUN update-ca-certificates

COPY ci/requirements-image.txt /tmp/requirements-image.txt
RUN python3 -m pip install --no-cache-dir --no-deps --require-hashes --only-binary=:all: \
      --index-url "$PIP_INDEX_URL" -r /tmp/requirements-image.txt \
 && rm /tmp/requirements-image.txt

COPY --from=outils /opt/raton/bin/ /usr/local/bin/
COPY plugin/scripts/ /opt/raton/scripts/
COPY plugin/schemas/ /opt/raton/schemas/
COPY plugin/regles/ /opt/raton/regles/
COPY plugin/references/ /opt/raton/references/

# Fichiers à root, en lecture seule pour l'utilisateur des jobs : un outil compromis ne
# peut pas modifier les règles ni les scripts de Raton.
RUN find /opt/raton -name __pycache__ -prune -exec rm -rf {} + \
 && chmod 0755 /opt/raton/scripts/*.py \
 && useradd --uid 10001 --user-group --no-create-home --home-dir /nonexistent --shell /usr/sbin/nologin raton

ENV PATH=/opt/raton/scripts:$PATH \
    PYTHONDONTWRITEBYTECODE=1
USER 10001
