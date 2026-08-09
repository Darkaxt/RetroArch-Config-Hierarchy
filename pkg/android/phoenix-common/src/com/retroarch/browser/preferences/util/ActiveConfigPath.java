package com.retroarch.browser.preferences.util;

/** Selects the config path shared by native and Android-side consumers. */
public final class ActiveConfigPath
{
   public interface DefaultPathProvider
   {
      String get();
   }

   private ActiveConfigPath()
   {
   }

   public static String select(String explicitPath, DefaultPathProvider defaultPathProvider)
   {
      if (explicitPath != null && !explicitPath.isEmpty())
         return explicitPath;

      return defaultPathProvider.get();
   }
}
