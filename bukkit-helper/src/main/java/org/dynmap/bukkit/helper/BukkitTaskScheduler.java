package org.dynmap.bukkit.helper;

import java.util.concurrent.Callable;
import java.util.concurrent.Future;

import org.bukkit.Bukkit;
import org.bukkit.World;
import org.bukkit.plugin.Plugin;
import org.bukkit.scheduler.BukkitScheduler;

/**
 * TaskScheduler for Bukkit/Spigot/Paper servers with a single main thread
 */
public class BukkitTaskScheduler implements TaskScheduler {

    private static BukkitScheduler scheduler() {
        return Bukkit.getScheduler();
    }

    @Override
    public void runSync(Plugin plugin, Runnable task, long delayTicks) {
        scheduler().scheduleSyncDelayedTask(plugin, task, delayTicks);
    }

    @Override
    public Object runTimer(Plugin plugin, Runnable task, long delayTicks, long periodTicks) {
        return scheduler().scheduleSyncRepeatingTask(plugin, task, delayTicks, periodTicks);
    }

    @Override
    public <T> Future<T> callSync(Plugin plugin, Callable<T> task) {
        return scheduler().callSyncMethod(plugin, task);
    }

    @Override
    public void runAt(Plugin plugin, World world, int chunkX, int chunkZ, Runnable task, long delayTicks) {
        if ((delayTicks <= 0) && Bukkit.isPrimaryThread()) {
            task.run();
            return;
        }
        scheduler().scheduleSyncDelayedTask(plugin, task, delayTicks);
    }

    @Override
    public void runAsync(Plugin plugin, Runnable task, long delayTicks) {
        scheduler().scheduleAsyncDelayedTask(plugin, task, delayTicks);
    }

    @Override
    public void cancelAll(Plugin plugin) {
        scheduler().cancelTasks(plugin);
    }
}
