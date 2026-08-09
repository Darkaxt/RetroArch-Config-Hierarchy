package com.retroarch.browser.preferences.util;

import java.io.BufferedInputStream;
import java.io.BufferedOutputStream;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.IOException;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.Arrays;

/**
 * Resolves the default master config without parsing or rewriting migration
 * sources. Android-specific directory selection remains in UserPreferences.
 */
public final class ConfigPathPolicy
{
   public enum StoragePolicy
   {
      PUBLIC,
      APP_SPECIFIC
   }

   public enum Outcome
   {
      EXISTING,
      MIGRATED,
      INITIALIZED
   }

   public static final class Result
   {
      private final File file;
      private final Outcome outcome;

      private Result(File file, Outcome outcome)
      {
         this.file = file;
         this.outcome = outcome;
      }

      public File file()
      {
         return file;
      }

      public Outcome outcome()
      {
         return outcome;
      }
   }

   private static final Object PUBLICATION_LOCK = new Object();
   private static final int COPY_BUFFER_SIZE = 64 * 1024;

   private ConfigPathPolicy()
   {
   }

   public static File publicConfigDirectory(File sharedStorageRoot)
   {
      return new File(sharedStorageRoot, "RetroArch");
   }

   public static Result resolve(StoragePolicy storagePolicy, File publicDirectory,
         File legacyExternalDirectory, File legacyInternalDirectory,
         File legacyFallbackDirectory, String fileName) throws IOException
   {
      return resolve(storagePolicy, publicDirectory, null, legacyExternalDirectory,
            legacyInternalDirectory, legacyFallbackDirectory, fileName);
   }

   public static Result resolve(StoragePolicy storagePolicy, File publicDirectory,
         File alternatePublicDirectory, File legacyExternalDirectory,
         File legacyInternalDirectory, File legacyFallbackDirectory,
         String fileName) throws IOException
   {
      validateFileName(fileName);

      if (storagePolicy == StoragePolicy.APP_SPECIFIC)
         return resolveAppSpecific(legacyExternalDirectory, legacyInternalDirectory,
               legacyFallbackDirectory, fileName);

      if (publicDirectory == null)
         throw new IOException("Public config directory is unavailable");

      ensureDirectory(publicDirectory);
      File destination = new File(publicDirectory, fileName);
      Result existing = existingFile(destination);
      if (existing != null)
         return existing;

      File source = firstLegacySource(fileName, alternatePublicDirectory,
            legacyExternalDirectory, legacyInternalDirectory, legacyFallbackDirectory);
      if (source != null)
         return migrate(source, destination);

      return initialize(destination);
   }

   private static Result resolveAppSpecific(File externalDirectory, File internalDirectory,
         File fallbackDirectory, String fileName) throws IOException
   {
      File selectedDirectory = externalDirectory != null ? externalDirectory
            : (internalDirectory != null ? internalDirectory : fallbackDirectory);
      if (selectedDirectory == null)
         throw new IOException("Application-specific config directory is unavailable");

      ensureDirectory(selectedDirectory);
      File selected = new File(selectedDirectory, fileName);
      Result existing = existingFile(selected);
      return existing != null ? existing : initialize(selected);
   }

   private static File firstLegacySource(String fileName, File... directories) throws IOException
   {
      for (File directory : directories)
      {
         if (directory == null)
            continue;

         File candidate = new File(directory, fileName);
         if (!candidate.exists())
            continue;
         if (!candidate.isFile() || !candidate.canRead())
            throw new IOException("Legacy config cannot be read: " + candidate);
         return candidate;
      }
      return null;
   }

   private static Result migrate(File source, File destination) throws IOException
   {
      File temporary = File.createTempFile("." + destination.getName() + ".migrate-",
            ".tmp", destination.getParentFile());
      IOException pendingFailure = null;

      try
      {
         byte[] sourceDigest = copyAndSync(source, temporary);
         if (source.length() != temporary.length())
            throw new IOException("Migrated config length verification failed");
         if (!Arrays.equals(sourceDigest, digest(temporary)))
            throw new IOException("Migrated config digest verification failed");

         synchronized (PUBLICATION_LOCK)
         {
            Result existing = existingFile(destination);
            if (existing != null)
               return existing;

            if (!temporary.renameTo(destination))
            {
               existing = existingFile(destination);
               if (existing != null)
                  return existing;
               throw new IOException("Could not publish migrated config to: " + destination);
            }
         }

         return new Result(destination, Outcome.MIGRATED);
      }
      catch (IOException failure)
      {
         pendingFailure = failure;
         throw failure;
      }
      finally
      {
         if (temporary.exists() && !temporary.delete())
         {
            IOException cleanupFailure = new IOException(
                  "Could not remove migration temporary file: " + temporary);
            if (pendingFailure != null)
               pendingFailure.addSuppressed(cleanupFailure);
            else
               throw cleanupFailure;
         }
      }
   }

   private static Result initialize(File destination) throws IOException
   {
      synchronized (PUBLICATION_LOCK)
      {
         Result existing = existingFile(destination);
         if (existing != null)
            return existing;
         if (!destination.createNewFile())
         {
            existing = existingFile(destination);
            if (existing != null)
               return existing;
            throw new IOException("Could not initialize config: " + destination);
         }
      }
      return new Result(destination, Outcome.INITIALIZED);
   }

   private static byte[] copyAndSync(File source, File destination) throws IOException
   {
      MessageDigest digest = sha256();
      byte[] buffer = new byte[COPY_BUFFER_SIZE];

      try (BufferedInputStream input = new BufferedInputStream(new FileInputStream(source));
           FileOutputStream fileOutput = new FileOutputStream(destination);
           BufferedOutputStream output = new BufferedOutputStream(fileOutput))
      {
         int count;
         while ((count = input.read(buffer)) != -1)
         {
            output.write(buffer, 0, count);
            digest.update(buffer, 0, count);
         }
         output.flush();
         fileOutput.getFD().sync();
      }

      return digest.digest();
   }

   private static byte[] digest(File file) throws IOException
   {
      MessageDigest digest = sha256();
      byte[] buffer = new byte[COPY_BUFFER_SIZE];
      try (BufferedInputStream input = new BufferedInputStream(new FileInputStream(file)))
      {
         int count;
         while ((count = input.read(buffer)) != -1)
            digest.update(buffer, 0, count);
      }
      return digest.digest();
   }

   private static MessageDigest sha256()
   {
      try
      {
         return MessageDigest.getInstance("SHA-256");
      }
      catch (NoSuchAlgorithmException impossible)
      {
         throw new IllegalStateException("SHA-256 is unavailable", impossible);
      }
   }

   private static Result existingFile(File file) throws IOException
   {
      if (!file.exists())
         return null;
      if (!file.isFile())
         throw new IOException("Config path is not a file: " + file);
      return new Result(file, Outcome.EXISTING);
   }

   private static void ensureDirectory(File directory) throws IOException
   {
      if (directory.isDirectory())
         return;
      if (directory.exists() || !directory.mkdirs())
         throw new IOException("Could not create config directory: " + directory);
   }

   private static void validateFileName(String fileName)
   {
      if (fileName == null || fileName.isEmpty() || !new File(fileName).getName().equals(fileName))
         throw new IllegalArgumentException("Config filename must be a non-empty basename");
   }
}
