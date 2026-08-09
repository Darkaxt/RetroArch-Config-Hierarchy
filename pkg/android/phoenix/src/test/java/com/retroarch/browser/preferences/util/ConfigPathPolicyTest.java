package com.retroarch.browser.preferences.util;

import static org.junit.Assert.assertArrayEquals;
import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertNotEquals;
import static org.junit.Assert.assertTrue;
import static org.junit.Assert.fail;

import java.io.File;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicReference;

import org.junit.Rule;
import org.junit.Test;
import org.junit.rules.TemporaryFolder;

public class ConfigPathPolicyTest
{
   @Rule
   public TemporaryFolder temporaryFolder = new TemporaryFolder();

   @Test
   public void existingPublicConfigWinsAndRemainsUntouched() throws Exception
   {
      File publicDir = temporaryFolder.newFolder("public");
      File externalDir = temporaryFolder.newFolder("external");
      File publicConfig = write(publicDir, "retroarch.cfg", "# public\nvalue = public\n");
      write(externalDir, "retroarch.cfg", "value = legacy\n");
      byte[] before = Files.readAllBytes(publicConfig.toPath());

      ConfigPathPolicy.Result result = ConfigPathPolicy.resolve(
            ConfigPathPolicy.StoragePolicy.PUBLIC, publicDir, externalDir, null, null, "retroarch.cfg");

      assertEquals(ConfigPathPolicy.Outcome.EXISTING, result.outcome());
      assertEquals(publicConfig.getCanonicalFile(), result.file().getCanonicalFile());
      assertArrayEquals(before, Files.readAllBytes(publicConfig.toPath()));
   }

   @Test
   public void externalLegacyConfigMigratesByteForByte() throws Exception
   {
      File publicDir = temporaryFolder.newFolder("public");
      File externalDir = temporaryFolder.newFolder("external");
      byte[] source = new byte[] {0, '#', '\n', 'x', '=', '1', '\n', (byte)0xff};
      Files.write(new File(externalDir, "retroarch.cfg").toPath(), source);

      ConfigPathPolicy.Result result = ConfigPathPolicy.resolve(
            ConfigPathPolicy.StoragePolicy.PUBLIC, publicDir, externalDir, null, null, "retroarch.cfg");

      assertEquals(ConfigPathPolicy.Outcome.MIGRATED, result.outcome());
      assertArrayEquals(source, Files.readAllBytes(result.file().toPath()));
   }

   @Test
   public void internalLegacyIsUsedOnlyWhenExternalLegacyIsMissing() throws Exception
   {
      File publicDir = temporaryFolder.newFolder("public");
      File externalDir = temporaryFolder.newFolder("external");
      File internalDir = temporaryFolder.newFolder("internal");
      write(internalDir, "retroarch.cfg", "source = internal\n");

      ConfigPathPolicy.Result result = ConfigPathPolicy.resolve(
            ConfigPathPolicy.StoragePolicy.PUBLIC, publicDir, externalDir, internalDir, null, "retroarch.cfg");

      assertEquals(ConfigPathPolicy.Outcome.MIGRATED, result.outcome());
      assertArrayEquals("source = internal\n".getBytes(StandardCharsets.UTF_8),
            Files.readAllBytes(result.file().toPath()));
   }

   @Test
   public void externalLegacyPrecedesInternalAndFallback() throws Exception
   {
      File publicDir = temporaryFolder.newFolder("public");
      File externalDir = temporaryFolder.newFolder("external");
      File internalDir = temporaryFolder.newFolder("internal");
      File fallbackDir = temporaryFolder.newFolder("fallback");
      write(externalDir, "core.cfg", "external");
      write(internalDir, "core.cfg", "internal");
      write(fallbackDir, "core.cfg", "fallback");

      ConfigPathPolicy.Result result = ConfigPathPolicy.resolve(
            ConfigPathPolicy.StoragePolicy.PUBLIC, publicDir, externalDir, internalDir, fallbackDir, "core.cfg");

      assertEquals("external", new String(Files.readAllBytes(result.file().toPath()), StandardCharsets.UTF_8));
   }

   @Test
   public void noExistingConfigInitializesEmptyPublicFile() throws Exception
   {
      File root = temporaryFolder.newFolder("root");
      File publicDir = new File(root, "RetroArch/config");

      ConfigPathPolicy.Result result = ConfigPathPolicy.resolve(
            ConfigPathPolicy.StoragePolicy.PUBLIC, publicDir, null, null, null, "retroarch.cfg");

      assertEquals(ConfigPathPolicy.Outcome.INITIALIZED, result.outcome());
      assertTrue(result.file().isFile());
      assertEquals(0, result.file().length());
   }

   @Test
   public void nullExternalLegacyLocationDoesNotHideInternalLegacy() throws Exception
   {
      File publicDir = temporaryFolder.newFolder("public");
      File internalDir = temporaryFolder.newFolder("internal");
      write(internalDir, "retroarch.cfg", "internal");

      ConfigPathPolicy.Result result = ConfigPathPolicy.resolve(
            ConfigPathPolicy.StoragePolicy.PUBLIC, publicDir, null, internalDir, null, "retroarch.cfg");

      assertEquals("internal", new String(Files.readAllBytes(result.file().toPath()), StandardCharsets.UTF_8));
   }

   @Test
   public void staleMigrationTemporaryFileCannotReplacePublicData() throws Exception
   {
      File publicDir = temporaryFolder.newFolder("public");
      File externalDir = temporaryFolder.newFolder("external");
      write(publicDir, ".retroarch.cfg.migrate-stale", "stale");
      write(externalDir, "retroarch.cfg", "source");

      ConfigPathPolicy.Result result = ConfigPathPolicy.resolve(
            ConfigPathPolicy.StoragePolicy.PUBLIC, publicDir, externalDir, null, null, "retroarch.cfg");

      assertEquals("source", new String(Files.readAllBytes(result.file().toPath()), StandardCharsets.UTF_8));
      assertNotEquals("stale", new String(Files.readAllBytes(result.file().toPath()), StandardCharsets.UTF_8));
   }

   @Test
   public void concurrentResolversNeverOverwritePublishedWinner() throws Exception
   {
      File publicDir = temporaryFolder.newFolder("public");
      File firstLegacy = temporaryFolder.newFolder("first");
      File secondLegacy = temporaryFolder.newFolder("second");
      write(firstLegacy, "retroarch.cfg", "first");
      write(secondLegacy, "retroarch.cfg", "second");
      CountDownLatch start = new CountDownLatch(1);
      AtomicReference<Throwable> failure = new AtomicReference<>();

      Thread first = resolverThread(start, failure, publicDir, firstLegacy);
      Thread second = resolverThread(start, failure, publicDir, secondLegacy);
      first.start();
      second.start();
      start.countDown();
      first.join();
      second.join();

      if (failure.get() != null)
         throw new AssertionError(failure.get());
      String winner = new String(Files.readAllBytes(new File(publicDir, "retroarch.cfg").toPath()),
            StandardCharsets.UTF_8);
      assertTrue(winner.equals("first") || winner.equals("second"));
   }

   @Test
   public void publicationFailureIsVisibleAndLeavesNoPartialAuthority() throws Exception
   {
      File publicDirAsFile = temporaryFolder.newFile("not-a-directory");
      File externalDir = temporaryFolder.newFolder("external");
      write(externalDir, "retroarch.cfg", "source");

      try
      {
         ConfigPathPolicy.resolve(ConfigPathPolicy.StoragePolicy.PUBLIC,
               publicDirAsFile, externalDir, null, null, "retroarch.cfg");
         fail("Expected publication failure");
      }
      catch (IOException expected)
      {
         assertFalse(new File(publicDirAsFile, "retroarch.cfg").exists());
      }
   }

   @Test
   public void appSpecificPolicyKeepsExistingPlayBehavior() throws Exception
   {
      File publicDir = temporaryFolder.newFolder("public");
      File externalDir = temporaryFolder.newFolder("external");
      File internalDir = temporaryFolder.newFolder("internal");
      write(publicDir, "retroarch.cfg", "public");
      write(internalDir, "retroarch.cfg", "internal");

      ConfigPathPolicy.Result result = ConfigPathPolicy.resolve(
            ConfigPathPolicy.StoragePolicy.APP_SPECIFIC, publicDir, externalDir, internalDir, null, "retroarch.cfg");

      assertEquals(ConfigPathPolicy.Outcome.INITIALIZED, result.outcome());
      assertEquals(new File(externalDir, "retroarch.cfg").getCanonicalFile(), result.file().getCanonicalFile());
      assertEquals(0, result.file().length());
   }

   private Thread resolverThread(CountDownLatch start, AtomicReference<Throwable> failure,
         File publicDir, File legacyDir)
   {
      return new Thread(() -> {
         try
         {
            start.await();
            ConfigPathPolicy.resolve(ConfigPathPolicy.StoragePolicy.PUBLIC,
                  publicDir, legacyDir, null, null, "retroarch.cfg");
         }
         catch (Throwable throwable)
         {
            failure.compareAndSet(null, throwable);
         }
      });
   }

   private File write(File directory, String name, String contents) throws IOException
   {
      File file = new File(directory, name);
      Files.write(file.toPath(), contents.getBytes(StandardCharsets.UTF_8));
      return file;
   }
}
