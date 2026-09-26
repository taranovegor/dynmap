package org.dynmap.bukkit.helper;

import java.util.concurrent.Callable;
import java.util.concurrent.Future;

import org.bukkit.World;
import org.bukkit.plugin.Plugin;

/**
 * Task scheduling. TaskSchedulers picks the implementation for the running server.
 */
public interface TaskScheduler {
    /**
     * Schedule task to run on server-safe thread (the global region on Folia)
     * @param plugin - owning plugin
     * @param run - runnable method
     * @param delay - delay in server ticks (50msec)
     */
    void runSync(Plugin plugin, Runnable run, long delay);

    /**
     * Schedule repeating task to run on server-safe thread
     * @param plugin - owning plugin
     * @param run - runnable method
     * @param delay - delay in server ticks (50msec)
     * @param period - period in server ticks (50msec)
     * @return task handle
     */
    Object runTimer(Plugin plugin, Runnable run, long delay, long period);

    /**
     * Call method on server-safe thread
     * @param plugin - owning plugin
     * @param task - callable method
     * @param <T> - return value type for method called
     * @return future for completion of call
     */
    <T> Future<T> callSync(Plugin plugin, Callable<T> task);

    /**
     * Schedule task to run on server-safe thread owning the given chunk (its region on Folia)
     * @param plugin - owning plugin
     * @param world - world
     * @param chunkX - chunk X
     * @param chunkZ - chunk Z
     * @param run - runnable method
     * @param delay - delay in server ticks (50msec)
     */
    void runAt(Plugin plugin, World world, int chunkX, int chunkZ, Runnable run, long delay);

    /**
     * Schedule task to run on asynchronous server thread
     * @param plugin - owning plugin
     * @param run - runnable method
     * @param delay - delay in server ticks (50msec)
     */
    void runAsync(Plugin plugin, Runnable run, long delay);

    /**
     * Cancel tasks owned by the given plugin
     * @param plugin - owning plugin
     */
    void cancelAll(Plugin plugin);
}
