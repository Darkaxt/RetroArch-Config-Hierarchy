package com.retroarch.browser.preferences.util;

import java.io.File;
import java.io.IOException;

import com.retroarch.BuildConfig;

import android.annotation.TargetApi;
import android.content.Context;
import android.content.SharedPreferences;
import android.media.AudioManager;
import android.media.AudioTrack;
import android.os.Build;
import android.preference.PreferenceManager;
import android.content.pm.PackageManager.NameNotFoundException;
import android.util.Log;

/**
 * Utility class for retrieving, saving, or loading preferences.
 */
public final class UserPreferences
{
	// Logging tag.
	private static final String TAG = "UserPreferences";

	// Disallow explicit instantiation.
	private UserPreferences()
	{
	}

	/**
	 * Retrieves the path to the default location of the libretro config.
	 * 
	 * @param ctx the current {@link Context}
	 * 
	 * @return the path to the default location of the libretro config.
	 */
	public static String getDefaultConfigPath(Context ctx)
	{
		return resolveDefaultConfig(ctx).file().getAbsolutePath();
	}

	/**
	 * Resolves the default config and reports whether it already existed, was
	 * migrated, or was freshly initialized.
	 */
	public static ConfigPathPolicy.Result resolveDefaultConfig(Context ctx)
	{
		final File internal = ctx.getFilesDir();
		File external = null;

		// Get the App's external storage folder
		final String state = android.os.Environment.getExternalStorageState();
		if (android.os.Environment.MEDIA_MOUNTED.equals(state))
			external = ctx.getExternalFilesDir(null);

		// Native library directory and data directory for this front-end.
		final String dataDir = ctx.getApplicationInfo().dataDir;
		final String coreDir = dataDir + "/cores/";

		// Get libretro name and path
		final SharedPreferences prefs = getPreferences(ctx);
		final String libretro_path = prefs.getString("libretro_path", coreDir);

		// Check if global config is being used. Return true upon failure.
		final boolean globalConfigEnabled = prefs.getBoolean("global_config_enable", true);

		String fileName;
		// If we aren't using the global config.
		if (!globalConfigEnabled && !libretro_path.equals(coreDir))
		{
			String sanitized_name = sanitizeLibretroPath(libretro_path);
			fileName = sanitized_name + ".cfg";
		}
		else // Using global config.
		{
			fileName = "retroarch.cfg";
		}

		ConfigPathPolicy.StoragePolicy storagePolicy = BuildConfig.PLAY_STORE_BUILD
				? ConfigPathPolicy.StoragePolicy.APP_SPECIFIC
				: ConfigPathPolicy.StoragePolicy.PUBLIC;
		File publicDirectory = null;
		if (!BuildConfig.PLAY_STORE_BUILD)
		{
			if (!android.os.Environment.MEDIA_MOUNTED.equals(state))
				throw new IllegalStateException("Shared storage is not mounted");
			publicDirectory = new File(android.os.Environment.getExternalStorageDirectory(),
					"RetroArch" + File.separator + "config");
		}

		try
		{
			return ConfigPathPolicy.resolve(storagePolicy, publicDirectory, external,
					internal, new File("/mnt/extsd"), fileName);
		}
		catch (IOException e)
		{
			throw new IllegalStateException("Failed to resolve RetroArch config", e);
		}
	}

	/**
	 * Updates the libretro configuration file
	 * with new values if version has changed.
	 * 
	 * @param ctx the current {@link Context}.
	 */
	public static void updateConfigFile(Context ctx)
	{
		updateConfigFile(ctx, getDefaultConfigPath(ctx));
	}

	/** Updates Android-specific values in an already selected config. */
	public static void updateConfigFile(Context ctx, String path)
	{
		ConfigFile config = new ConfigFile(path);

		final String dataDir = ctx.getApplicationInfo().dataDir;
		final String coreDir = dataDir + "/cores/";
		final String dstPath	= dataDir;
		final String dstPathSubdir = "assets";

		final SharedPreferences prefs = getPreferences(ctx);

		config.setString("libretro_directory", coreDir);

		int samplingRate = getOptimalSamplingRate(ctx);
		if (samplingRate != -1) {
			config.setInt("audio_out_rate", samplingRate);
		}

		try
		{
			int version      = ctx.getPackageManager().getPackageInfo(ctx.getPackageName(), 0).versionCode;
			int last_version = config.keyExists("bundle_assets_extract_last_version") ?
					config.getInt("bundle_assets_extract_last_version") : 0;

			if (version == last_version)
				return;

			config.setString("bundle_assets_src_path", ctx.getApplicationInfo().sourceDir);
			config.setString("bundle_assets_dst_path", dstPath);
			config.setString("bundle_assets_dst_path_subdir", dstPathSubdir);
			config.setInt("bundle_assets_extract_version_current", version);
		}
		catch (NameNotFoundException ignored)
		{
		}

		// Refactor this entire mess and make this usable for per-core config
		if (Build.VERSION.SDK_INT >= 17 && prefs.getBoolean("audio_latency_auto", true))
		{
			int bufferSize = getLowLatencyBufferSize(ctx);
			if (bufferSize != -1) {
				config.setInt("audio_block_frames", bufferSize);
			}
		}

		try
		{
			Log.i(TAG, "Writing config to: " + path);
			Log.i(TAG, "dst dir is: " + dstPath);
			Log.i(TAG, "dst subdir is: " + dstPathSubdir);
			config.write(path);
		}
		catch (IOException e)
		{
			throw new IllegalStateException("Failed to save config file to: " + path, e);
		}
	}

	private static void readbackString(ConfigFile cfg, SharedPreferences.Editor edit, String key)
	{
		if (cfg.keyExists(key))
			edit.putString(key, cfg.getString(key));
		else
			edit.remove(key);
	}

	private static void readbackBool(ConfigFile cfg, SharedPreferences.Editor edit, String key)
	{
		if (cfg.keyExists(key))
			edit.putBoolean(key, cfg.getBoolean(key));
		else
			edit.remove(key);
	}

	private static void readbackDouble(ConfigFile cfg, SharedPreferences.Editor edit, String key)
	{
		if (cfg.keyExists(key))
			edit.putFloat(key, (float)cfg.getDouble(key));
		else
			edit.remove(key);
	}

	/*
	private static void readbackFloat(ConfigFile cfg, SharedPreferences.Editor edit, String key)
	{
		if (cfg.keyExists(key))
			edit.putFloat(key, cfg.getFloat(key));
		else
			edit.remove(key);
	}
	*/

	/**
	private static void readbackInt(ConfigFile cfg, SharedPreferences.Editor edit, String key)
	{
		if (cfg.keyExists(key))
			edit.putInt(key, cfg.getInt(key));
		else
			edit.remove(key);
	}
	*/

	/**
	 * Sanitizes a libretro core path.
	 * 
	 * @param path The path to the libretro core.
	 * 
	 * @return the sanitized libretro path.
	 */
	private static String sanitizeLibretroPath(String path)
	{
		String sanitized_name = path.substring(
				path.lastIndexOf('/') + 1,
				path.lastIndexOf('.'));
		sanitized_name = sanitized_name.replace("neon", "");
		sanitized_name = sanitized_name.replace("libretro_", "");

		return sanitized_name;
	}

	/**
	 * Gets a {@link SharedPreferences} instance containing current settings.
	 * 
	 * @param ctx the current {@link Context}.
	 * 
	 * @return A SharedPreference instance containing current settings.
	 */
	public static SharedPreferences getPreferences(Context ctx)
	{
		return PreferenceManager.getDefaultSharedPreferences(ctx);
	}

	/**
	 * Gets the optimal sampling rate for low-latency audio playback.
	 * 
	 * @param ctx the current {@link Context}.
	 * 
	 * @return the optimal sampling rate for low-latency audio playback in Hz.
	 */
	@TargetApi(17)
	private static int getLowLatencyOptimalSamplingRate(Context ctx)
	{
		AudioManager manager = (AudioManager) ctx.getSystemService(Context.AUDIO_SERVICE);
		String value = manager.getProperty(AudioManager.PROPERTY_OUTPUT_SAMPLE_RATE);

		if(value == null || value.isEmpty()) {
			return -1;
		}

		return Integer.parseInt(value);
	}

	/**
	 * Gets the optimal buffer size for low-latency audio playback.
	 * 
	 * @param ctx the current {@link Context}.
	 * 
	 * @return the optimal output buffer size in decimal PCM frames.
	 */
	@TargetApi(17)
	private static int getLowLatencyBufferSize(Context ctx)
	{
		AudioManager manager = (AudioManager) ctx.getSystemService(Context.AUDIO_SERVICE);
		String value = manager.getProperty(AudioManager.PROPERTY_OUTPUT_FRAMES_PER_BUFFER);

		if(value == null || value.isEmpty()) {
			return -1;
		}

		int buffersize = Integer.parseInt(value);
		Log.i(TAG, "Queried ideal buffer size (frames): " + buffersize);
		return buffersize;
	}

	/**
	 * Gets the optimal audio sampling rate.
	 * <p>
	 * On Android 4.2+ devices this will retrieve the optimal low-latency sampling rate,
	 * since Android 4.2 adds support for low latency audio in general.
	 * <p>
	 * On other devices, it simply returns the regular optimal sampling rate
	 * as returned by the hardware.
	 * 
	 * @param ctx The current {@link Context}.
	 * 
	 * @return the optimal audio sampling rate in Hz.
	 */
	private static int getOptimalSamplingRate(Context ctx)
	{
		int ret;
		if (Build.VERSION.SDK_INT >= 17)
			ret = getLowLatencyOptimalSamplingRate(ctx);
		else
			ret = AudioTrack.getNativeOutputSampleRate(AudioManager.STREAM_MUSIC);

		Log.i(TAG, "Using sampling rate: " + ret + " Hz");
		return ret;
	}
}
