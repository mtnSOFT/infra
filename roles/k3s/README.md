# k3s

Installs a k3s Kubernetes cluster and bootstraps cert-manager and ArgoCD.

## What it does

- Installs k3s; the first node is the **master** (hostname default `k3s-1` or defined by k3s_master variable), the rest join as agents
- Master runs with `--cluster-init --flannel-backend=host-gw`; agents join via the master IP + node token
- Installs KVM/libvirt packages
- Installs cert-manager and creates a self-signed internal Root CA `ClusterIssuer`
- Deploys ArgoCD (stable) with a Traefik `IngressRoute` and an internally-signed cert
- Installs kubectl aliases/helpers in `/etc/profile.d`

## Key variables

- `k3s_master` — inventory host that is the master (default `k3s-1`)
- `cert_manager_version` — cert-manager release (default `v1.14.0`)
- `kubeconfig` — path to kubeconfig (default `/etc/rancher/k3s/k3s.yaml`)
- `argocd_hostname` — host for the ArgoCD ingress (define in inventory)

## Usage

`ansible-playbook -i inventories/production/hosts playbooks/k3s.yml`

Targets the `k3s` inventory group. The initial ArgoCD admin password is printed during the run.
