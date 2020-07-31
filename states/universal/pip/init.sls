
# Install python packages that I want system-wide on all platforms
install_universal_system_wide_python_packages:
  pip.installed:
    - names:
      - IPython
