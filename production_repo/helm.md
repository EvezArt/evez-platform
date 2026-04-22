# HELM CHART - Production Kubernetes Deployment

# Chart.yaml
apiVersion: v2
name: kiloclaw
version: 0.1.0
description: Event-driven AI revenue execution system
type: application

# values.yaml
replicaCount:
  ingestor: 2
  qualifier: 3
  router: 2
  closer: 2
  pricing: 1
  product: 1
  learning: 1

image:
  repository: kiloclaw
  tag: latest
  pullPolicy: IfNotPresent

kafka:
  enabled: true
  bootstrapServers: kafka:9092

postgres:
  enabled: true
  host: postgres
  port: 5432
  database: ledger
  user: econ

tenancy:
  isolationEnabled: true
  defaultQuota: 1000

resources:
  ingestor:
    limits:
      cpu: 500m
      memory: 512Mi
  qualifier:
    limits:
      cpu: 1000m
      memory: 1Gi
  router:
    limits:
      cpu: 2000m
      memory: 4Gi
      nvidia.com/gpu: 1
  closer:
    limits:
      cpu: 500m
      memory: 512Mi
  learning:
    limits:
      cpu: 1000m
      memory: 2Gi

autoscaling:
  enabled: true
  minReplicas: 1
  maxReplicas: 10
  targetCPUUtilizationPercentage: 70

service:
  type: ClusterIP
  ports:
    api: 8000
    kafka: 9092
    postgres: 5432

# templates/deployment-ingestor.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: ingestor
  labels:
    app: ingestor
spec:
  replicas: {{ .Values.replicaCount.ingestor }}
  selector:
    matchLabels:
      app: ingestor
  template:
    metadata:
      labels:
        app: ingestor
    spec:
      containers:
        - name: ingestor
          image: "{{ .Values.image.repository }}/ingestor:{{ .Values.image.tag }}"
          env:
            - name: KAFKA_BROKER
              value: "{{ .Values.kafka.bootstrapServers }}"
            - name: TENANT_ISOLATION
              value: "{{ .Values.tenancy.isolationEnabled }}"
          ports:
            - containerPort: 8000
          resources:
            {{- toYaml .Values.resources.ingestor | nindent 12 }}

# templates/deployment-router.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: gpu-router
spec:
  replicas: {{ .Values.replicaCount.router }}
  template:
    spec:
      containers:
        - name: router
          image: "{{ .Values.image.repository }}/router:{{ .Values.image.tag }}"
          env:
            - name: MODEL_POOL
              value: "{{ .Values.modelPool }}"
          resources:
            limits:
              nvidia.com/gpu: {{ .Values.resources.router.limits.nvidia.com.gpu }}

# templates/service-kafka.yaml
apiVersion: v1
kind: Service
metadata:
  name: kafka
spec:
  ports:
    - port: 9092
      targetPort: 9092
  selector:
    app: kafka

# templates/ingress.yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: api-gateway
  annotations:
    nginx.ingress.kubernetes.io/proxy-read-timeout: "300"
spec:
  rules:
    - host: {{ .Values.domain }}
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: api-gateway
                port:
                  number: 8000

# templates/configmap.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: kiloclaw-config
data:
  kafka.bootstrap: "{{ .Values.kafka.bootstrapServers }}"
  tenancy.isolation: "{{ .Values.tenancy.isolationEnabled }}"