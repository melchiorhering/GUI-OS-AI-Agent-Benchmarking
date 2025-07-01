# Portable Ubuntu VM with Docker and QEMU/KVM

This project provides a complete environment for creating and managing a portable, KVM-accelerated Ubuntu Desktop VM inside a Docker container.

_Build once with QEMU/KVM, run anywhere with the **`qemux/qemu`** Docker image._

---

## 📂 Docker Directory Layout

```text
📆docker
┣ 📦observation-server    # Observation Code
┃ ┣ 📂src
┃ ┃ ┣ 📜__init__.py
┃ ┃ ┣ 📜pyxcursor.py      # Overlaying the cursor on the screenshot
┃ ┃ ┣ 📜recording.py      # Functions for recording the video and keyboard/mouse input
┃ ┃ ┗ 📜utils.py          # Util functions
┃ ┣ 📜main.py
┃ ┗ 📜pyproject.toml
┣ 📂vms
┃ ┗ 📂ubuntu-base
┃   ├ 📌boot.iso            # Installer ISO (can be deleted post-install)
┃   └ 📂storage             # Directory for data.img, qemu.mac, uefi.rom, uefi.vars
┃     ├ 📌data.img          # The VM's disk image; created during install
┃     ├ 📌qemu.mac          # Auto-generated on container start
┃     ├ 📌uefi.rom          # Auto-generated on container start
┃     └ 📌uefi.vars         # Auto-generated on container start
├ 📌README.md
├ 📌base_download.py
├ 📌base_upload.py
├ 📌compose.qemu.yaml
├ 📌1-os-configuration.sh             # OS-level setup and configuration
├ 📌2-python-configuration.sh         # Python environment setup and configuration
├ 📌3-startup-servers.sh              # Script to setup startup scripts for the following services
├ 📌4-jupyter-kernel-gateway.sh       # Jupyter Kernel Gateway startup script
└ 📌5-fastapi-observation-server.sh   # FastAPI Observation server script
```

## 1 · Host Prerequisites

| Role                | Required packages / actions                    |
| :------------------ | :--------------------------------------------- |
| **Builder & Runtime** | Docker Engine, Docker Compose                  |
|                     | Add your user to the `docker` and `kvm` groups |

***Verify Hardware Virtualization:** Run `kvm-ok` (on Ubuntu) or `cat /proc/cpuinfo | grep -E "vmx|svm"`. If your host is itself a VM, you must enable **nested VT-x/AMD-V** in your hypervisor settings.*

The `qemux/qemu` image includes all necessary QEMU and OVMF components, so no extra QEMU packages are needed on the host.

-----

## 2 · Getting Started

You have two options to get your VM running. Building from scratch is recommended for a clean, customized environment.

### Option A: Build From Scratch

This path guides you through installing a fresh Ubuntu OS.

#### Step 1: Configure and Launch the Installer

1.  **Define the `ROOT_DIR` variable** in your environment, or manually replace `${ROOT_DIR}` in `compose.qemu.yaml` with the absolute path to your project root.

2.  **Uncomment the `BOOT` environment variable** in `compose.qemu.yaml` to automatically download the latest Ubuntu LTS installer on the first run.

    ```yaml
    # In compose.qemu.yaml
    environment:
      BOOT: "ubuntu" # SET THIS ONCE FOR THE FIRST CONTAINER BUILD/RUN
      RAM_SIZE: "4G"
      # ...
    ```

3.  **Launch the Docker container.** This will download the ISO, create a blank `data.img` disk, and start the VM in an installation environment.

    ```bash
    docker compose -f compose.qemu.yaml up -d
    ```

#### Step 2: Perform the Interactive OS Install

1.  **Open the web console** by navigating to **`http://localhost:8006`** in your browser.
2.  Follow the Ubuntu installer prompts. **When asked where to install, select the `/storage/data.img` disk.**
3.  After the installation is complete, **shut the VM down** from within the guest OS. Do not just stop the container.

#### Step 3: Configure for Normal Boot

Your OS is now installed on `data.img`. This file is your "golden disk." To boot from it directly, you must modify `compose.qemu.yaml`:

1.  **Comment out the `BOOT` variable** you set earlier.

2.  **Swap the volume mounts.** Comment out the `boot.iso` line and uncomment the `data.img` line.

    ```diff
    # In compose.qemu.yaml
    volumes:
    -  # - ${ROOT_DIR}/src/docker/vms/ubuntu-base/boot.iso:/boot.iso
    +  - ${ROOT_DIR}/src/docker/vms/ubuntu-base/data.img:/boot.img # When image is created use this to start the image
    ...
    environment:
    - # BOOT: "ubuntu"
    ```

3.  **Start your new VM\!**

    ```bash
    docker compose -f compose.qemu.yaml up -d
    ```

    The container will now boot directly from your installed `data.img` disk. You can now proceed to the OS Setup steps.

### Option B: Use a Pre-built Image

If you want to skip the OS installation, you can download a pre-built base image from Hugging Face.

1.  **Download the image files:**
    You can use the provided Python script:
    ```bash
    uv run base_download.py # --args
    ```
    Or, if you have the `vms` directory configured as a GIT submodule:
    ```sh
    # Change directory to the submodule
    cd src/docker/vms
    # Pull the latest variant
    git pull origin main
    ```
2.  **Configure `compose.qemu.yaml`** to boot directly from the downloaded `data.img` as shown in **Step 3** of "Option A" above.
3.  **Start the container:**
    ```bash
    docker compose -f compose.qemu.yaml up -d
    ```

-----

*The `compose.qemu.yaml` file remains below for reference.*

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
      # FIRST INSTALL
      # - ${ROOT_DIR}/src/docker/vms/ubuntu-base/boot.iso:/boot.iso # when you have a local image file
      # - ${ROOT_DIR}/src/docker/vms/ubuntu-base/storage:/storage # Setting the storage directory

      # WHEN INSTALLED
      - ${ROOT_DIR}/src/docker/vms/ubuntu-base/storage/data.img:/boot.img # When image has been created use this to startup the VM.
      - ${ROOT_DIR}/src/docker/shared:/shared # Shared directory for the VM; in the container you have to mount `mount -t 9p -o trans=virtio shared /mnt/container`

    # Grant KVM + networking devices
    devices:
      - /dev/kvm
      - /dev/net/tun
    cap_add:
      - NET_ADMIN

    # Runtime tweaks
    environment:
      # BOOT: "https://releases.ubuntu.com/jammy/ubuntu-22.04.5-desktop-amd64.iso" downloads and install a new iso image
      BOOT: "ubuntu" # SET THIS ONCE FOR THE FIRST CONTAINER BUILD/RUN  (THIS DOWNLOADS THE LATEST ISO)
      RAM_SIZE: "4G" # ↑ RAM (default 2G)
      CPU_CORES: "4" # ↑ vCPUs (default 2)
      DISK_SIZE: "25g" # Set this to resize the disk
      DEBUG: "Y"
      # ARGUMENTS: # Optional: You can create the ARGUMENTS environment variable to provide additional arguments to QEMU at runtime

    ports:
      - 8006:8006 # Web console (noVNC)
      - 2222:22   # SSH from host → guest
      - 8888:8888 # Jupyter Kernel Gateway
      - 8765:8765 # FastAPI Observation server

    restart: unless-stopped
    stop_grace_period: 2m
```
## 4 · Setting Up the OS

After the initial Ubuntu installation is complete, the next phase involves configuring the operating system, installing development tools, and setting up your application servers. This process begins with establishing SSH access.

### 4.1 · First Boot: Establishing SSH Access

For the very first boot after installation, you must use the web-based noVNC console to get inside the VM and install the SSH server. This is a one-time setup step.

1.  **Start the VM without the `BOOT` variable**.
    * In your `compose.qemu.yaml`, make sure to comment out the `boot.iso` line and uncomment the `data.img` line to boot from your newly installed system:
        ```diff
        - # - ${ROOT_DIR}/src/docker/vms/ubuntu-base/boot.iso:/boot.iso
        + - ${ROOT_DIR}/src/docker/vms/ubuntu-base/data.img:/boot.img
        ```
    * Then, start the container:
        ```bash
        docker compose -f compose.qemu.yaml up -d
        ```

2.  **Log in via noVNC.** Open **`http://localhost:8006`** and log in to the Ubuntu desktop using the user account you created during installation.

3.  **Install and Enable OpenSSH Server.** Open a terminal inside the VM (from the desktop) and run the following commands to install the SSH server and ensure it starts automatically on boot:
    ```bash
    # Update package list
    sudo apt update

    # Install the OpenSSH server package
    sudo apt install -y openssh-server

    # Enable the sshd service to start on boot
    sudo systemctl enable sshd # or ssh

    # Start the service immediately
    sudo systemctl start sshd # or ssh
    ```

4.  **Verify SSH is running.** You can check its status to confirm it's active:
    ```bash
    sudo systemctl status sshd # or ssh
    ```
    With the SSH server now running on port 22 inside the VM (and mapped to port 2222 on your host), you can proceed with all other steps from your local machine's terminal.

### 4.2 · Copy and Execute Configuration Scripts

Now that SSH is working, you can copy the provisioning scripts from your host machine to the VM and execute them.

1.  **Copy the scripts to the VM.** Open a new terminal on your **host machine** and use `scp` to transfer the files.
    ```bash
    # From your host machine (ensure you are in the project's 'docker' directory)
    scp -P 2222 ./1-os-configuration.sh user@localhost:/home/user/
    scp -P 2222 ./2-python-configuration.sh user@localhost:/home/user/
    scp -P 2222 ./3-startup-servers.sh user@localhost:/home/user/
    scp -P 2222 ./4-jupyter-kernel-gateway.sh user@localhost:/home/user/
    scp -P 2222 ./5-fastapi-observation-server.sh user@localhost:/home/user/
    ```
    *(Note: If you encounter "connection refused," double-check that the VM is running and that you completed step 4.1 successfully.)*

2.  **Connect to the VM via SSH.**
    ```bash
    ssh user@localhost -p 2222
    ```

3.  **Make the scripts executable inside the VM.**
    ```bash
    # Inside the VM guest (via SSH)
    chmod +x /home/user/*.sh
    ```

4.  **Run the OS Configuration Script.** This script handles system updates, essential package installation, passwordless sudo setup, and SSH server configuration.
    ```bash
    # Inside the VM guest
    sudo /home/user/1-os-configuration.sh
    ```
    This script will:
    * Perform `apt update` and `dist-upgrade`.
    * Install core packages like `openssh-server`, `curl`, `wget`, `git`, `htop`, `net-tools`, `build-essential`, `gnome-screenshot`, and Python development packages for GUI automation (`python3-tk`, `python3-dev`, `scrot`).
    * Configure passwordless `sudo` for the `user` account via a `sudoers.d` drop-in file.
    * Set up the SSH daemon with a minimal configuration (Port 22, Password Authentication enabled, Pubkey Authentication disabled) in `/etc/ssh/sshd_config.d/10-sandbox.conf` and enable `sshd` to start at boot.
    * **Create and enable the `jupyter-kg.service` and `observation-server.service` systemd unit files** in `/etc/systemd/system/` to ensure Jupyter Kernel Gateway and the FastAPI Observation Server start automatically at boot.

5.  **Run the Python Environment Script.** This will set up the Python virtual environment and install all necessary packages.
    ```bash
    # Inside the VM guest
    /home/user/2-python-configuration.sh
    ```
    This script will:
    * Install `uv`, a fast Python package installer.
    * Create a Python virtual environment at `~/Desktop/.action-env` using Python 3.11.
    * Install core Python packages including `jupyter_kernel_gateway`, `fastapi`, `uvicorn`, `pyautogui`, `requests`, `numpy`, `pandas`, `ipywidgets`, `smolagents`, `ipykernel`, `opencv-python`, `torch`, `Pillow`, and `pynput`.
    * Verify the Jupyter kernelspec list.

### 4.3 · Deploy the Observation Server Code

After the main setup, deploy your FastAPI observation server code to the VM. The `rsync` command is ideal for this.

```bash
# From your host machine, sync your local observation server directory to the VM
rsync -avz -e "ssh -p 2222" ./observation-server/ user@localhost:/home/user/observation-server/
```

## 5 · Finalizing the Setup

After the configuration scripts have run, a few manual steps are required to ensure the graphical environment is stable and the services are running correctly.

### 5.1 · Reboot the VM

First, perform a full reboot to ensure all system changes and new services are loaded properly.

```bash
# Inside the VM guest (via SSH or the desktop terminal)
sudo reboot
```

Give the VM a minute to restart, then log back in via the noVNC console or SSH.

### 5.2 · Configure the Desktop for GUI Automation (Important)

These steps are essential for tools like `pyautogui` to function correctly. You must perform them from the **noVNC console** (`http://localhost:8006`).

#### 1\. Switch from Wayland to X11

Most GUI automation tools require the Xorg (X11) display server. Ubuntu's default, Wayland, is often incompatible.

  - On the graphical login screen, click the gear icon (⚙️) in the bottom-right corner and select **"Ubuntu on Xorg"** before entering your password.
  - To make this change permanent:
    1.  Edit the GDM3 configuration file:
        ```bash
        sudo nano /etc/gdm3/custom.conf
        ```
    2.  Uncomment the line `#WaylandEnable=false` by removing the `#`.
    3.  Save the file (`Ctrl+O`), exit (`Ctrl+X`), and restart the display manager:
        ```bash
        sudo systemctl restart gdm3
        ```

> ### **Critical Fix for X11 Black Screen Bug**
>
> A known bug in some Ubuntu versions can cause a black screen with only a mouse cursor after logging into an X11 session. This is due to a PAM module issue. More details can be found in this [Reddit thread](https://www.reddit.com/r/Ubuntu/comments/1cdcqjs/dark_screen_with_crossshaped_cursor_after_logging/).
>
> **To fix this**, edit `/etc/pam.d/login` and comment out the `pam_lastlog.so` line:
>
> ```sh
> sudo nano /etc/pam.d/login
>
> # Comment out the following line by adding a '#' at the beginning:
> # session optional pam_lastlog.so
> ```


#### 2. Verify the `XAUTHORITY` Path

The systemd services need to know where to find the X11 authentication file to control the GUI.

1.  After logging into the desktop graphically, open a terminal and find the path:
    ```bash
    echo $XAUTHORITY
    # Example output: /run/user/1000/gdm/Xauthority
    ```
2.  Check if this path matches the one in the service files. If it's different, you **must** update them.
    ```bash
    # Example for the Jupyter service
    sudo nano /etc/systemd/system/jupyter-kg.service
    ```
3.  Update the `Environment="XAUTHORITY=..."` line with the correct path, save the file, then reload the systemd daemon and restart the services:
    ```bash
    sudo systemctl daemon-reload
    sudo systemctl restart jupyter-kg.service
    sudo systemctl restart observation-server.service
    ```

## 6 · Verify Services

After rebooting and applying any necessary fixes, confirm that the background services are running.

```bash
# Inside the VM guest
systemctl status jupyter-kg.service --no-pager
systemctl status observation-server.service --no-pager
```

Look for `Active: active (running)`. To monitor their live logs for errors:

```bash
journalctl -u jupyter-kg.service -f
# Press Ctrl+C to stop, then check the other service
journalctl -u observation-server.service -f
```

You can also find persistent log files in `~/.local/share/jupyter-kg-logs/` and `~/.local/share/fastapi-observation-logs/`.

-----

## 7 · Post-Configuration Application Installation

With the core system configured and verified, you can now install any additional GUI applications you need for development or automation tasks.

### 7.1 · Visual Studio Code

```bash
# Using Snap is recommended on Ubuntu
sudo snap install code --classic
```

### 7.2 · LibreOffice Suite

```bash
# Using Snap for a sandboxed, up-to-date version
sudo snap install libreoffice
```

### 7.3 · Chromium Browser

```bash
# Install Chromium for web automation tasks
sudo snap install chromium
```

-----

## 8 · Software Summary

Here is a recap of the key packages installed by the provisioning scripts.

| Category       | Packages                                          |
| :------------- | :-------------------------------------------------- |
| Dev Tools      | `build-essential`, `git`, `curl`, `wget`, `uv`      |
| GUI Automation | `gnome-screenshot`, `pyautogui`, `pynput`, `Pillow` |
| Network / Misc | `openssh-server`, `net-tools`, `htop`               |

-----

## 9 · Developing Inside the VM with VS Code

The most efficient way to work inside the VM is with VS Code's Remote-SSH extension.

1.  **Install** the [Remote - SSH](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-ssh) extension in your local VS Code.
2.  Press `F1` (or `Ctrl+Shift+P`) and select **Remote-SSH: Connect to Host…**.
3.  Enter the connection details: `user@localhost:2222`.
4.  VS Code will connect, install its server components in the VM, and open a new window.

You are now effectively using VS Code from *within* the VM, with direct access to its terminal, filesystem, and applications.

-----

## 🚀 Conclusion

You now have a **portable, reproducible Ubuntu VM** running under Docker/KVM, with:

  - One-file cloning and backup (`data.img`)
  - Password-based SSH and passwordless `sudo` for easy access
  - A stable X11 environment for robust GUI automation
  - Seamless development via VS Code Remote-SSH
  - **Jupyter Kernel Gateway and a FastAPI Observation Server, both starting automatically on boot\!**

Happy hacking\! 🎉
