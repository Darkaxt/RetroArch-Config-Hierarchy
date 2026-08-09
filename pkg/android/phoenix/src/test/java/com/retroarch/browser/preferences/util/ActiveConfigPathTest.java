package com.retroarch.browser.preferences.util;

import static org.junit.Assert.assertEquals;

import java.util.concurrent.atomic.AtomicInteger;

import org.junit.Test;

public class ActiveConfigPathTest
{
   @Test
   public void explicitNonEmptyPathWinsWithoutResolvingDefault()
   {
      AtomicInteger fallbackCalls = new AtomicInteger();

      String selected = ActiveConfigPath.select("/caller/custom.cfg", () -> {
         fallbackCalls.incrementAndGet();
         return "/public/retroarch.cfg";
      });

      assertEquals("/caller/custom.cfg", selected);
      assertEquals(0, fallbackCalls.get());
   }

   @Test
   public void emptyExplicitPathUsesDefaultResolver()
   {
      assertEquals("/public/retroarch.cfg",
            ActiveConfigPath.select("", () -> "/public/retroarch.cfg"));
   }

   @Test
   public void absentExplicitPathUsesDefaultResolver()
   {
      assertEquals("/public/retroarch.cfg",
            ActiveConfigPath.select(null, () -> "/public/retroarch.cfg"));
   }
}
