[Project Root](../../README.md) > [Roles](../README.md) > **zfs**

# zfs

Installs ZFS on Debian: enables the `contrib` apt component when it is missing (installing `software-properties-common`
first, for `apt-add-repository`), then installs the kernel headers and image for the host architecture plus `dpkg-dev`,
`zfs-dkms`, and `zfsutils-linux`. Pool import and datasets are not managed here.
