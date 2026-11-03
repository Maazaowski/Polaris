"""Entry point for: python -m polaris.intake"""

from polaris.config import settings
from polaris.intake.watcher import start_profile_watcher

if __name__ == "__main__":
    print("Polaris Profile Watcher")
    print(f"  Global inbound: {settings.inbound_dir}")
    print(f"  Profiles dir:   {settings.supplier_profiles_dir}")
    settings.ensure_directories()
    start_profile_watcher(blocking=True)
