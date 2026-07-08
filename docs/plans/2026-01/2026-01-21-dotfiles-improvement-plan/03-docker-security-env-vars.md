# Plan: Docker Security and Environment Variables

## Problem Statement

The Docker Compose configuration (`roles/docker/files/docker-compose.yml`) has several security issues and missing
configurations:

1. **Undefined environment variables** referenced but never defined
2. **Host networking** used where bridge networking would suffice
3. **No resource limits** on containers
4. **Docker socket exposed** to Glance container
5. **Missing health checks** for service monitoring
6. **No secrets management** for sensitive values

## Current State Analysis

### Issue 1: Undefined Environment Variables

**Line 39** - PiHole references undefined variable:
```yaml
- FTLCONF_webserver_api_password  # Never defined\!
```

**Line 185** - Glance references missing .env file:
```yaml
env_file: .env  # File does not exist\!
```

### Issue 2: Host Networking (Security Risk)

**Line 54** - Plex uses host networking:
```yaml
network_mode: host  # TODO: Temporary for docker/plex weirdness
```

**Line 168** - Home Assistant uses host networking:
```yaml
network_mode: host  # TODO: does this need to be host?
```

Host networking bypasses Docker network isolation, exposing all ports.

### Issue 3: Docker Socket Exposure

**Line 190** - Glance has read access to Docker socket:
```yaml
- /var/run/docker.sock:/var/run/docker.sock:ro
```

This allows the container to query Docker (intended for the containers widget), but is a security consideration.

### Issue 4: No Resource Limits

No containers have memory or CPU limits, risking resource exhaustion.

---

## Implementation Tasks

### Phase 1: Create Environment Configuration

- [ ] **Task 1.1**: Create `.env.example` template
  ```bash
  # roles/docker/files/.env.example

  # PiHole Configuration
  FTLCONF_webserver_api_password=your_secure_password_here

  # Glance Configuration
  GLANCE_WEATHER_API_KEY=your_openweathermap_key

  # Timezone
  TZ=America/Los_Angeles
  ```

- [ ] **Task 1.2**: Add `.env` to role deployment
  ```yaml
  # roles/docker/tasks/main.yml
  - name: Check if .env exists
    stat:
      path: "{{ docker_compose_dir }}/.env"
    register: env_file

  - name: Warn if .env missing
    debug:
      msg: "WARNING: .env file missing. Copy .env.example and configure."
    when: not env_file.stat.exists
  ```

- [ ] **Task 1.3**: Add vault-encrypted secrets for production values
  ```yaml
  # inventory/group_vars/nas/vault.yml (encrypted)
  vault_pihole_password: "encrypted_password"
  vault_glance_api_key: "encrypted_key"
  ```

### Phase 2: Fix Network Configuration

- [ ] **Task 2.1**: Replace Plex host networking with bridge + port mapping
  ```yaml
  plex:
    image: linuxserver/plex
    container_name: plex
    # network_mode: host  # Removed
    ports:
      - "32400:32400"     # Plex Media Server
      - "3005:3005"       # Plex Companion
      - "8324:8324"       # Roku via Plex Companion
      - "32469:32469"     # Plex DLNA Server
      - "1900:1900/udp"   # Plex DLNA Server
      - "32410:32410/udp" # GDM network discovery
      - "32412:32412/udp" # GDM network discovery
      - "32413:32413/udp" # GDM network discovery
      - "32414:32414/udp" # GDM network discovery
  ```

- [ ] **Task 2.2**: Evaluate Home Assistant networking needs
  ```yaml
  # Home Assistant may legitimately need host networking for:
  # - mDNS/Bonjour discovery
  # - USB device access
  # - Bluetooth integration
  #
  # If only web interface needed, use bridge:
  homeassistant:
    ports:
      - "8123:8123"
  ```

- [ ] **Task 2.3**: Create dedicated Docker network
  ```yaml
  networks:
    media:
      driver: bridge
    homelab:
      driver: bridge

  services:
    plex:
      networks:
        - media
    sonarr:
      networks:
        - media
  ```

### Phase 3: Add Resource Limits

- [ ] **Task 3.1**: Add memory limits to resource-intensive services
  ```yaml
  plex:
    deploy:
      resources:
        limits:
          memory: 4G
        reservations:
          memory: 1G

  transmission:
    deploy:
      resources:
        limits:
          memory: 1G

  homeassistant:
    deploy:
      resources:
        limits:
          memory: 2G
  ```

### Phase 4: Add Health Checks

- [ ] **Task 4.1**: Add health checks to critical services
  ```yaml
  plex:
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:32400/identity"]
      interval: 30s
      timeout: 10s
      retries: 3

  pihole:
    healthcheck:
      test: ["CMD", "dig", "@127.0.0.1", "pi.hole"]
      interval: 30s
      timeout: 10s
      retries: 3

  transmission:
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:9091"]
      interval: 30s
      timeout: 10s
      retries: 3
  ```

### Phase 5: Documentation

- [ ] **Task 5.1**: Create `roles/docker/README.md` with security notes
- [ ] **Task 5.2**: Document required environment variables
- [ ] **Task 5.3**: Add troubleshooting guide for common issues

---

## Security Recommendations Summary

| Issue | Severity | Fix |
|-------|----------|-----|
| Undefined env vars | High | Create .env with secrets from vault |
| Host networking | Medium | Use bridge + explicit ports where possible |
| Docker socket | Low | Accept risk for monitoring, or remove widget |
| No resource limits | Medium | Add deploy.resources.limits |
| No health checks | Low | Add healthcheck configurations |

## Files to Modify/Create

| File | Action |
|------|--------|
| `roles/docker/files/docker-compose.yml` | Fix networking, add limits |
| `roles/docker/files/.env.example` | Create template |
| `roles/docker/tasks/main.yml` | Add env file handling |
| `inventory/host_vars/nas/vault.yml` | Add encrypted secrets |
| `roles/docker/README.md` | Document configuration |

## Validation Checklist

- [ ] `.env.example` created with all required variables
- [ ] Ansible vault contains encrypted values
- [ ] Docker Compose validates successfully
- [ ] All services start without errors
- [ ] Plex accessible on port 32400 (if changed from host mode)
- [ ] Health checks report healthy status
- [ ] Memory limits applied correctly

## Risk Assessment

- **High Risk**: Changing Plex networking may break remote access
- **Mitigation**: Test bridge mode thoroughly, keep host mode as fallback
- **Testing**: Validate all services after changes
- **Rollback**: Keep original docker-compose.yml backed up
