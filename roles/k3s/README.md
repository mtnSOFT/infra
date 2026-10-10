# k3s

Installs a k3s Kubernetes cluster and bootstraps cert-manager and ArgoCD.

## What it does

- Installs k3s; the first node is the **master** (hostname default `k3s-1` or defined by k3s_master variable), the rest join as agents
- Master runs with `--cluster-init --flannel-backend=host-gw`; agents join via the master IP + node token
- Installs KVM/libvirt packages
- Installs cert-manager and creates a self-signed internal Root CA `ClusterIssuer`
- Deploys ArgoCD at a pinned release with a Traefik `IngressRoute` and an internally-signed cert
- Installs kubectl aliases/helpers in `/etc/profile.d`

## Key variables

- `k3s_master` — inventory host that is the master (default `k3s-1`)
- `cert_manager_version` — cert-manager release (default `v1.14.0`), applied on every run
- `argocd_version` — ArgoCD release (default `v3.5.1`), applied on every run
- `k3s_install_version` — k3s release passed to the installer as `INSTALL_K3S_VERSION`
  (default `v1.36.3+k3s1`). Affects **new nodes only**: the install task is guarded with
  `creates: /usr/local/bin/k3s`, so changing this never upgrades an existing node. Upgrading
  k3s in place is a separate, manual operation, and a k3s minor is a Kubernetes minor — apply
  them one at a time.
- `kubeconfig` — path to kubeconfig (default `/etc/rancher/k3s/k3s.yaml`)
- `argocd_hostname` — host for the ArgoCD ingress (define in inventory)

The three version variables are updated by Renovate — see
[Dependency updates](../../README.md#dependency-updates).

## Usage

`ansible-playbook -i inventories/production/hosts playbooks/k3s.yml`

Targets the `k3s` inventory group. The initial ArgoCD admin password is printed during the run.
