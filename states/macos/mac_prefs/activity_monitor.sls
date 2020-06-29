# Show the main window when launching Activity Monitor
launch_with_main_window:
  macdefaults.write:
    - domain: com.apple.ActivityMonitor
    - name: OpenMainWindow
    - value: true
    - vtype: bool
    - user: {{ grains.user }}
    - require:
      - close_system_prefs

# Visualize CPU usage in the Activity Monitor Dock icon
cpu_usage_in_dock_icon:
  macdefaults.write:
    - domain: com.apple.ActivityMonitor
    - name: IconType
    - value: 5
    - vtype: int
    - user: {{ grains.user }}
    - require:
      - close_system_prefs

# Show all processes in Activity Monitor
show_all_processes:
  macdefaults.write:
    - domain: com.apple.ActivityMonitor
    - name: ShowCategory
    - value: 0
    - vtype: int
    - user: {{ grains.user }}
    - require:
      - close_system_prefs
      
# Sort Activity Monitor results by CPU usage
sort_by_cpu_usage:
  macdefaults.write:
    - domain: com.apple.ActivityMonitor
    - name: SortColumn
    - value: 'CPUUsage'
    - vtype: string
    - user: {{ grains.user }}
    - require:
      - close_system_prefs

sort_direction:
  macdefaults.write:
    - domain: com.apple.ActivityMonitor
    - name: SortDirection
    - value: 0
    - vtype: int
    - user: {{ grains.user }}
    - require:
      - close_system_prefs
