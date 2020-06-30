# TODO: Template out this repo link so I can make these dotfiles public
# Clone work dotfiles repo
clone_work_dotfiles:
  git.latest:
    - name: git@github.pie.apple.com:connor-mason/dotfiles.git
    - rev: salt   # TODO: change to master
    - target: {{ grains.states_dir }}/work
    - identity: {{ grains.home }}/.ssh/id_rsa
    - force_clone: true

include:
  - .work
