package org.dynmap.bukkit.helper;

import org.bukkit.plugin.Plugin;

/**
 * Picks the TaskScheduler for the running server. Support for another platform is added as
 * one more implementation here.
 */
public final class TaskSchedulers {

    private static final TaskScheduler INSTANCE = create();

    private TaskSchedulers() {
    }

    public static TaskScheduler get() {
        return INSTANCE;
    }

    private static TaskScheduler create() {
        if (isRegionized()) {
            return new FoliaTaskScheduler();
        }
        return new BukkitTaskScheduler();
    }

    private static boolean isRegionized() {
        try {
            Class.forName("io.papermc.paper.threadedregions.RegionizedServer");
            return true;
        } catch (Throwable t) {
            return false;
        }
    }

    /**
     * Get dynmap plugin - for components that don't hold a plugin reference
     * @return plugin
     */
    public static Plugin dynmap() {
        Plugin plugin = org.bukkit.Bukkit.getPluginManager().getPlugin("dynmap");
        if (plugin == null) {
            throw new IllegalStateException("dynmap plugin is not registered");
        }
        return plugin;
    }
}
