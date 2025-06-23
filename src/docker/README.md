# QEMU/KVM (Docker) Ubuntu Base Image

For an initial base image you can download the following files from https://huggingface.co/datasets/melchiorhering/vms.
Use the `base_download.py` to download the files from this HF repo.
Or pull it using GIT submodules:

```sh

cd src/docker/vms

git pull origin main
```


_Build once with QEMU/KVM, run anywhere with the **`qemux/qemu`** Docker image_

---

## 📂 Docker Directory Layout

```text
📆docker
┣ 📦observation-server
┃ ┣ 📂src
┃ ┃ ┣ 📜__init__.py
┃ ┃ ┣ 📜pyxcursor.py
┃ ┃ ┣ 📜recording.py
┃ ┃ ┗ 📜utils.py
┃ ┣ 📜main.py
┃ ┗ 📜pyproject.toml
┣ 📂vms # A prebuild Ubuntu base image can be downloaded from you can download from https://huggingface.co/datasets/melchiorhering/vms
┃ ┗ 📂ubuntu-base
┃   ├ 📌boot.iso            # Installer ISO
┃   └ 📂storage            # Directory for data.img, qemu.mac, uefi.rom, uefi.vars
┃     ├ 📌data.img         # Disk image created during install
┃     ├ 📌qemu.mac         # created on container start
┃     ├ 📌uefi.rom         # created on container start
┃     └ 📌uefi.vars        # created on container start
├ 📌README.md
├ 📌base_download.py
├ 📌base_upload.py
├ 📌compose.qemu.yaml
├ 📌1-os-configuration.sh          # OS-level setup and configuration
├ 📌2-python-configuration.sh      # Python environment setup and configuration
├ 📌3-startup-servers.sh           # Script to setup startup scripts for the following services
├ 📌4-jupyter-kernel-gateway.sh    # Jupyter Kernel Gateway startup script
└ 📌5-fastapi-observation-server.sh # FastAPI Observation server script
```

> **Tip:** After you have installed the OS, **_only_ `data.img` matters**.
> `boot.iso` can be deleted; the container boots directly from the disk image.

---

## 1 · Overview

We use **QEMU/KVM** via the [`qemux/qemu`](<https://github.com/qemus/qemu>) Docker image to build and run Ubuntu (or any x86_64 distro). Set `BOOT=ubuntu` on the first run and the container downloads the official installer ISO automatically.

---

## 2 · Host prerequisites

| Role                  | Required packages / actions                      |
| :-------------------- | :----------------------------------------------- |
| **Builder & runtime** | Docker Engine, Docker Compose                    |
|                       | Add your user to the `docker` _and_ `kvm` groups |

_Verify hardware VT:_ `kvm-ok` _(Ubuntu)_ or `cat /proc/cpuinfo | grep -E "vmx|svm"`. If the host is itself a VM, turn on **nested VT‑x/AMD‑V**.

The `qemux/qemu` image already ships QEMU & OVMF, so the host needs no extra QEMU packages.

---

## 3 · Interactive OS Install (Docker Compose)

Create `compose.qemu.yaml` using the provided content. Note the use of `${ROOT_DIR}` which should be set in your environment or replaced with the absolute path to your project's root.

```yaml
# Global VM resource settings
# Configuration can be found here: https://github.com/qemus/qemu
# THIS DOCKER COMPOSE FILE IS USED FOR SETTING UP THE BASE VM ENVIRONMENT
services:
  ubuntu-base:
    image: qemux/qemu
    container_name: ubuntu-base

    # Mount the qcow2 we built earlier as /boot.qcow2 (overrides BOOT)
    volumes:
      # - ${ROOT_DIR}/src/docker/vms/ubuntu-base-snap1.qcow2:/boot.qcow2 # For using snapshots
      - ${ROOT_DIR}/src/docker/vms/ubuntu-base/boot.iso:/boot.iso
      - ${ROOT_DIR}/src/docker/vms/ubuntu-base/storage:/storage # Setting the storage directory
      - ${ROOT_DIR}/src/docker/shared/ubuntu-base:/shared # Shared directory for the VM; in the container you have to mount `mount -t 9p -o trans=virtio shared /mnt/container`
      # - ${ROOT_DIR}/src/docker/vms/ubuntu-base/data.img:/boot.img # When image is created use this to start the image

    # Grant KVM + networking devices
    devices:
      - /dev/kvm
      - /dev/net/tun
    cap_add:
      - NET_ADMIN

    # Runtime tweaks
    environment:
      # BOOT: "https://releases.ubuntu.com/jammy/ubuntu-22.04.5-desktop-amd64.iso" downloads and install a new iso image
      # BOOT: "ubuntu" # SET THIS ONCE FOR THE FIRST CONTAINER BUILD/RUN  (THIS DOWNLOADS THE LATEST ISO)
      RAM_SIZE: "4G" # ↑ RAM (default 2G)
      CPU_CORES: "4" # ↑ vCPUs (default 2)
      DISK_SIZE: "25g" # Set this to resize the disk
      DEBUG: "Y"
      # ARGUMENTS: # Optional: You can create the ARGUMENTS environment variable to provide additional arguments to QEMU at runtime

    ports:
      - 8006:8006 # Web console (noVNC)
      - 2222:22 # SSH from host → guest
      - 8888:8888 # Jupyter Kernel Gateway
      - 8765:8765 # FastAPI Observation server

    restart: unless-stopped
    stop_grace_period: 2m

```

```bash
docker compose -f compose.qemu.yaml up -d
```

1.  Open **`http://localhost:8006`** → run the Ubuntu installer to `/storage/data.img`. The `data.img` file will be created inside the `./docker/vms/ubuntu-base/storage/` directory on your host.
2.  When done, **shut the VM down** from inside the guest.

Now `data.img` is your golden disk; keep it safe, copy it to `snapshots/` for new VMs.

**Important Note on Volumes:**
The `compose.qemu.yaml` uses commented-out lines for `data.img` as `/boot.img` and the `shared` volume. For subsequent VM boots _after_ installation, you should uncomment the line for `data.img` to boot directly from your installed OS disk image:
` - ${ROOT_DIR}/src/docker/vms/ubuntu-base/data.img:/boot.img`
And comment out the `boot.iso` line:
` # - ${ROOT_DIR}/src/docker/vms/ubuntu-base/boot.iso:/boot.iso`
If you wish to use the `shared` volume, you will need to uncomment its line in `compose.qemu.yaml` as well and follow the mounting instructions provided in the comments: `mount -t 9p -o trans=virtio shared /mnt/example`.

---

## 4 · Automated First-boot Provisioning

After the initial Ubuntu installation is complete and the VM has been shut down, you'll apply the configurations using the provided scripts.



### 4.1 · Initial Access and Script Preparation

Start the VM again (without `BOOT=ubuntu`). For this _first time_ configuration, you will need to access the guest VM through the **noVNC console** (at `http://localhost:8006`).

1.  **Log in to the VM via noVNC** using the default `user` account (and its initial password from installation).

2.  **Copy the configuration scripts to the VM.** Since the `shared` volume is commented out by default in `compose.qemu.yaml`, `scp` is the primary method for initial script transfer.

    ```bash
    # From your host machine (assuming you are in the 'docker' directory)
    # Ensure the VM is running and its SSH server is reachable on port 2222
    scp -P 2222 ./1-os-configuration.sh user@localhost:/home/user/
    scp -P 2222 ./2-python-configuration.sh user@localhost:/home/user/
    scp -P 2222 ./3-startup-servers.sh user@localhost:/home/user/
    scp -P 2222 ./4-jupyter-kernel-gateway.sh user@localhost:/home/user/
    scp -P 2222 ./5-fastapi-observation-server.sh user@localhost:/home/user/
    ```

    **Troubleshooting SSH during initial copy:** If `scp` fails with "Connection reset by peer" or similar errors, it likely means the SSH server within the VM is not yet fully started or configured. In this case, you will need to:

    - Confirm the VM is fully booted via the noVNC console.
    - Log in via noVNC and manually check the SSH service status: `sudo systemctl status sshd`. Start it if necessary: `sudo systemctl start sshd`.
    - Alternatively, for this initial copy, you can manually create the script files using `nano` in the VM's terminal and paste their content if `scp` is not working.

3.  **Make the scripts executable inside the VM:**

    ```bash
    # Inside the VM guest (via noVNC console or SSH, once connected)
    chmod +x /home/user/1-os-configuration.sh
    chmod +x /home/user/2-python-configuration.sh
    chmod +x /home/user/3-jupyter-kernel-gateway.sh
    chmod +x /home/user/scripts/start-observation-server.sh
    ```

### 4.2 · Run OS-level Configuration

Execute the OS-level configuration script first. This script handles system updates, essential package installation, passwordless sudo setup, and SSH server configuration, including the systemd service for Jupyter Kernel Gateway.

```bash
# Inside the VM guest (via noVNC console or SSH, once connected)
sudo /home/user/1-os-configuration.sh
```

This script will:

- Perform `apt update` and `dist-upgrade`.
- Install core packages like `openssh-server`, `curl`, `wget`, `git`, `htop`, `net-tools`, `build-essential`, `gnome-screenshot`, and Python development packages for GUI automation (`python3-tk`, `python3-dev`, `scrot`).
- Configure passwordless `sudo` for the `user` account via a `sudoers.d` drop-in file.
- Set up the SSH daemon with a minimal configuration (Port 22, Password Authentication enabled, Pubkey Authentication disabled) in `/etc/ssh/sshd_config.d/10-sandbox.conf` and enable `sshd` to start at boot.
- **Create and enable the `jupyter-kg.service` and `observation-server.service` systemd unit files** in `/etc/systemd/system/` to ensure Jupyter Kernel Gateway and the FastAPI Observation Server start automatically at boot.

### 4.3 · Run Python Environment Configuration

Next, execute the Python environment setup script. This script installs `uv`, creates a virtual environment, and installs all necessary Python packages.

```bash
# Inside the VM guest (via noVNC console or SSH, after 4.2 completes)
/home/user/2-python-configuration.sh
```

This script will:

- Install `uv`, a fast Python package installer.
- Create a Python virtual environment at `~/Desktop/.action-env` using Python 3.11.
- Install core Python packages including `jupyter_kernel_gateway`, `fastapi`, `uvicorn`, `pyautogui`, `requests`, `numpy`, `pandas`, `ipywidgets`, `smolagents`, `ipykernel`, `opencv-python`, `torch`, `Pillow`, and `pynput`.
- Verify the Jupyter kernelspec list.

### 4.4 · Deploy the Observation Server Code

After the main setup, deploy your FastAPI observation server code to the VM. The `rsync` command is ideal for this as it efficiently syncs directories.

```bash
# From your host machine, sync your local observation server directory to the VM
rsync -avz -e "ssh -p 2222" /path/to/your/local/observation-server/ user@localhost:/home/user/observation-server/
```

_Replace `/path/to/your/local/observation/` with the actual path on your machine._

---

## 5 · Post-Configuration Application Installation (Manual)

The following applications are not included in the automated scripts and need to be installed manually after the core setup.

### 5.1 · VS Code

You can install VS Code from the command line using `snap` or by downloading the `.deb` package.

**Using Snap (Recommended on Ubuntu):**

```bash
sudo snap install code --classic
```

### 5.2 · LibreOffice

LibreOffice is typically available in the default Ubuntu repositories.

**Using APT (Recommended on Ubuntu):**

```bash
sudo snap install libreoffice
```

### 5.3 · Chromium Browser

Install Chromium via `snap` for simplicity:

```bash
sudo snap install chromium
```

---

## 6 · Post-Configuration Verification and Manual Steps

After running the configuration scripts, **a reboot of the VM is highly recommended** to ensure all services start correctly.

### 6.1 · Verify Services

After rebooting, you can check the status of the services:

```bash
# Inside the VM guest
systemctl status jupyter-kg.service --no-pager
systemctl status observation-server.service --no-pager
```

Look for "Active: active (running)". To monitor live logs:

```bash
journalctl -u jupyter-kg.service -f
journalctl -u observation-server.service -f
```

You can also check the script-specific logs in `~/.local/share/jupyter-kg-logs/` and `~/.local/share/fastapi-observation-logs/`.

### 6.2 · Important Manual Verifications (Crucial for GUI Automation)

1.  **Verify the `XAUTHORITY` path:** The systemd services rely on the correct `XAUTHORITY` path for `pyautogui` to interact with the GUI. After a graphical login to the VM, open a terminal and run `echo $XAUTHORITY`.
    - If this path is different from the one configured in `/etc/systemd/system/`, you **MUST** manually edit the service files (`sudo nano /etc/systemd/system/jupyter-kg.service`, etc.) to update the `XAUTHORITY` environment variable.
    - After editing, run `sudo systemctl daemon-reload` and `sudo systemctl restart <service-name>`.
2.  **Wayland to Xorg (X11) Switch:** For `pyautogui` to function, the VM needs to use X11 instead of Wayland. If your Ubuntu version defaults to Wayland, you **MUST** manually switch to Xorg (X11) on the login screen.
    - **To do this permanently:**
      1.  Edit `/etc/gdm3/custom.conf` (`sudo nano /etc/gdm3/custom.conf`).
      2.  Uncomment the line `WaylandEnable=false`.
      3.  Save the file and restart with `sudo systemctl restart gdm3`.

---

## 7 · Installed packages recap

| Category       | Packages                                            |
| :------------- | :-------------------------------------------------- |
| Dev tools      | `build-essential`, `git`, `curl`, `wget`, `uv`      |
| GUI helpers    | `gnome-screenshot`, `pyautogui`, `pynput`, `Pillow` |
| Network / misc | `openssh-server`, `net-tools`, `htop`               |

---

## 8 · Working with the VM from VS Code

1.  **Install** the _Remote - SSH_ extension in VS Code.
2.  Press `F1` → **Remote-SSH: Connect to Host…** → `user@localhost:2222`.
3.  The extension copies its server bits, then opens a new VS Code window that runs _inside_ your Ubuntu VM.
4.  From there you can modify config files, install software, or run terminals as if you were on a local machine.

---

## 🚀 Conclusion

You now have a **portable, reproducible Ubuntu VM** running under Docker/KVM, with:

- One‑file cloning (`data.img`)
- Password‑only SSH + passwordless sudo
- GUI automation via X11 & `pyautogui`
- Seamless development through VS Code Remote‑SSH
- **Jupyter Kernel Gateway and a FastAPI Observation Server starting automatically on machine boot\!**

Happy hacking\! 🎉
