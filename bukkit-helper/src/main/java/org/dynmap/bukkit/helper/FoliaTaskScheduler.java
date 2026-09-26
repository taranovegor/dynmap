package org.dynmap.bukkit.helper;

import java.lang.reflect.Method;
import java.util.concurrent.Callable;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.Future;
import java.util.function.Consumer;

import org.bukkit.Bukkit;
import org.bukkit.World;
import org.bukkit.plugin.Plugin;

/**
 * TaskScheduler for Folia. The Folia API isn't on the compile classpath, so the scheduler
 * methods are called reflectively and a method the server doesn't provide is ignored.
 */
public class FoliaTaskScheduler implements TaskScheduler {

    private final Object globalScheduler;
    private final Object regionScheduler;
    private final Object asyncScheduler;

    private final Method globalExecute;
    private final Method globalRun;
    private final Method globalRunDelayed;
    private final Method globalRunAtFixedRate;
    private final Method globalCancel;

    private final Method regionExecute;
    private final Method regionRun;
    private final Method regionRunDelayed;

    private final Method asyncRunNow;
    private final Method asyncRunDelayed;
    private final Method asyncCancel;

    public FoliaTaskScheduler() {
        Object global = getter("getGlobalRegionScheduler");
        Object region = getter("getRegionScheduler");
        Object async = getter("getAsyncScheduler");
        this.globalScheduler = global;
        this.regionScheduler = region;
        this.asyncScheduler = async;

        this.globalExecute = find(global, "execute", Plugin.class, Runnable.class);
        this.globalRun = find(global, "run", Plugin.class, Consumer.class);
        this.globalRunDelayed = find(global, "runDelayed", Plugin.class, Consumer.class, long.class);
        this.globalRunAtFixedRate = find(global, "runAtFixedRate", Plugin.class, Consumer.class, long.class, long.class);
        this.globalCancel = find(global, "cancelTasks", Plugin.class);

        this.regionExecute = find(region, "execute", Plugin.class, World.class, int.class, int.class, Runnable.class);
        this.regionRun = find(region, "run", Plugin.class, World.class, int.class, int.class, Consumer.class);
        this.regionRunDelayed = find(region, "runDelayed", Plugin.class, World.class, int.class, int.class, Consumer.class, long.class);

        this.asyncRunNow = find(async, "runNow", Plugin.class, Consumer.class);
        this.asyncRunDelayed = find(async, "runDelayed", Plugin.class, Consumer.class, long.class);
        this.asyncCancel = find(async, "cancelTasks", Plugin.class);
    }

    @Override
    public void runSync(Plugin plugin, Runnable task, long delayTicks) {
        if (delayTicks > 0) {
            invoke(globalRunDelayed, globalScheduler, plugin, toConsumer(task), delayTicks);
        } else if (globalExecute != null) {
            invoke(globalExecute, globalScheduler, plugin, task);
        } else {
            invoke(globalRun, globalScheduler, plugin, toConsumer(task));
        }
    }

    @Override
    public Object runTimer(Plugin plugin, Runnable task, long delayTicks, long periodTicks) {
        return invokeForResult(globalRunAtFixedRate, globalScheduler, plugin, toConsumer(task), delayTicks, periodTicks);
    }

    @Override
    public <T> Future<T> callSync(Plugin plugin, final Callable<T> task) {
        final CompletableFuture<T> future = new CompletableFuture<T>();
        runSync(plugin, new Runnable() {
            public void run() {
                try {
                    future.complete(task.call());
                } catch (Throwable t) {
                    future.completeExceptionally(t);
                }
            }
        }, 0);
        return future;
    }

    @Override
    public void runAt(Plugin plugin, World world, int chunkX, int chunkZ, Runnable task, long delayTicks) {
        if (delayTicks > 0) {
            invoke(regionRunDelayed, regionScheduler, plugin, world, chunkX, chunkZ, toConsumer(task), delayTicks);
        } else if (regionExecute != null) {
            invoke(regionExecute, regionScheduler, plugin, world, chunkX, chunkZ, task);
        } else {
            invoke(regionRun, regionScheduler, plugin, world, chunkX, chunkZ, toConsumer(task));
        }
    }

    @Override
    public void runAsync(Plugin plugin, Runnable task, long delayTicks) {
        if ((delayTicks > 0) && (asyncRunDelayed != null)) {
            invoke(asyncRunDelayed, asyncScheduler, plugin, toConsumer(task), delayTicks);
        } else {
            invoke(asyncRunNow, asyncScheduler, plugin, toConsumer(task));
        }
    }

    @Override
    public void cancelAll(Plugin plugin) {
        invoke(globalCancel, globalScheduler, plugin);
        invoke(asyncCancel, asyncScheduler, plugin);
    }

    private static Object getter(String name) {
        try {
            Object server = Bukkit.getServer();
            Method m = server.getClass().getMethod(name);
            m.setAccessible(true);
            return m.invoke(server);
        } catch (Throwable t) {
            logFailure(name, t);
            return null;
        }
    }

    private static Method find(Object target, String name, Class<?>... params) {
        if (target == null) {
            return null;
        }
        try {
            Method m = target.getClass().getMethod(name, params);
            m.setAccessible(true);
            return m;
        } catch (Throwable t) {
            return null;
        }
    }

    private static void invoke(Method method, Object target, Object... args) {
        if ((method == null) || (target == null)) {
            return;
        }
        try {
            method.invoke(target, args);
        } catch (Throwable t) {
            logFailure(method.getName(), t);
        }
    }

    private static Object invokeForResult(Method method, Object target, Object... args) {
        if ((method == null) || (target == null)) {
            return null;
        }
        try {
            return method.invoke(target, args);
        } catch (Throwable t) {
            logFailure(method.getName(), t);
            return null;
        }
    }

    private static Consumer<Object> toConsumer(final Runnable task) {
        return new Consumer<Object>() {
            public void accept(Object ignored) {
                task.run();
            }
        };
    }

    private static void logFailure(String name, Throwable t) {
        System.out.println("[dynmap] Folia scheduler " + name + " failed: " + t);
    }
}
