{{/*
File: templates/_helpers.tpl
Template helper functions for mern-microservices chart
*/}}

{{/*
Expand the name of the chart.
*/}}
{{- define "mern-microservices.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
We truncate at 63 chars because some Kubernetes name fields are limited to this (by the DNS naming spec).
If release name contains chart name it will be used as a full name.
*/}}
{{- define "mern-microservices.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{/*
Create chart name and version as used by the chart label.
*/}}
{{- define "mern-microservices.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "mern-microservices.labels" -}}
helm.sh/chart: {{ include "mern-microservices.chart" . }}
{{ include "mern-microservices.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- with .Values.commonLabels }}
{{ toYaml . }}
{{- end }}
{{- end }}

{{/*
Selector labels
*/}}
{{- define "mern-microservices.selectorLabels" -}}
app.kubernetes.io/name: {{ include "mern-microservices.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Create the name of the service account to use
*/}}
{{- define "mern-microservices.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "mern-microservices.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}

{{/*
Hello Service labels
*/}}
{{- define "mern-microservices.helloService.labels" -}}
{{ include "mern-microservices.labels" . }}
app.kubernetes.io/component: hello-service
{{- end }}

{{/*
Hello Service selector labels
*/}}
{{- define "mern-microservices.helloService.selectorLabels" -}}
{{ include "mern-microservices.selectorLabels" . }}
app.kubernetes.io/component: hello-service
{{- end }}

{{/*
Hello Service full name
*/}}
{{- define "mern-microservices.helloService.fullname" -}}
{{- if .Values.helloService.fullnameOverride }}
{{- .Values.helloService.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" (include "mern-microservices.fullname" .) .Values.helloService.name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}

{{/*
Profile Service labels
*/}}
{{- define "mern-microservices.profileService.labels" -}}
{{ include "mern-microservices.labels" . }}
app.kubernetes.io/component: profile-service
{{- end }}

{{/*
Profile Service selector labels
*/}}
{{- define "mern-microservices.profileService.selectorLabels" -}}
{{ include "mern-microservices.selectorLabels" . }}
app.kubernetes.io/component: profile-service
{{- end }}

{{/*
Profile Service full name
*/}}
{{- define "mern-microservices.profileService.fullname" -}}
{{- if .Values.profileService.fullnameOverride }}
{{- .Values.profileService.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" (include "mern-microservices.fullname" .) .Values.profileService.name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}

{{/*
Frontend labels
*/}}
{{- define "mern-microservices.frontend.labels" -}}
{{ include "mern-microservices.labels" . }}
app.kubernetes.io/component: frontend
{{- end }}

{{/*
Frontend selector labels
*/}}
{{- define "mern-microservices.frontend.selectorLabels" -}}
{{ include "mern-microservices.selectorLabels" . }}
app.kubernetes.io/component: frontend
{{- end }}

{{/*
Frontend full name
*/}}
{{- define "mern-microservices.frontend.fullname" -}}
{{- if .Values.frontend.fullnameOverride }}
{{- .Values.frontend.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" (include "mern-microservices.fullname" .) .Values.frontend.name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}

{{/*
Image pull secrets
*/}}
{{- define "mern-microservices.imagePullSecrets" -}}
{{- if .Values.global.imagePullSecrets }}
imagePullSecrets:
{{- range .Values.global.imagePullSecrets }}
  - name: {{ . }}
{{- end }}
{{- end }}
{{- end }}

{{/*
Common annotations
*/}}
{{- define "mern-microservices.annotations" -}}
{{- with .Values.commonAnnotations }}
{{ toYaml . }}
{{- end }}
{{- end }}

{{/*
Image name helper
*/}}
{{- define "mern-microservices.image" -}}
{{- $registry := .Values.global.registry -}}
{{- $repository := .Values.global.repository -}}
{{- $tag := .tag -}}
{{- printf "%s/%s:%s" $registry $repository $tag }}
{{- end }}

{{/*
Environment variables helper
*/}}
{{- define "mern-microservices.env" -}}
{{- range $key, $value := .env }}
- name: {{ $key }}
  value: {{ $value | quote }}
{{- end }}
{{- end }}

{{/*
Resource limits helper
*/}}
{{- define "mern-microservices.resources" -}}
{{- if .resources }}
resources:
  {{- if .resources.limits }}
  limits:
    {{- if .resources.limits.cpu }}
    cpu: {{ .resources.limits.cpu }}
    {{- end }}
    {{- if .resources.limits.memory }}
    memory: {{ .resources.limits.memory }}
    {{- end }}
  {{- end }}
  {{- if .resources.requests }}
  requests:
    {{- if .resources.requests.cpu }}
    cpu: {{ .resources.requests.cpu }}
    {{- end }}
    {{- if .resources.requests.memory }}
    memory: {{ .resources.requests.memory }}
    {{- end }}
  {{- end }}
{{- end }}
{{- end }}