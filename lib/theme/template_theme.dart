import 'package:flutter/material.dart';

import '../core/config/app_capabilities.dart';

class TemplateTokens {
  const TemplateTokens({
    required this.name,
    required this.background,
    required this.surface,
    required this.primary,
    required this.secondary,
    required this.onMedia,
    required this.posterTint,
    required this.radius,
    required this.homeHeadline,
    required this.dramaHook,
    required this.walletPitch,
    required this.playerModeLabel,
  });

  final String name;
  final Color background;
  final Color surface;
  final Color primary;
  final Color secondary;
  final Color onMedia;
  final Color posterTint;
  final double radius;
  final String homeHeadline;
  final String dramaHook;
  final String walletPitch;
  final String playerModeLabel;
}

TemplateTokens templateTokensFor(StyleTemplate template, Color brandPrimary) {
  return switch (template) {
    StyleTemplate.hongguoInspired => TemplateTokens(
        name: 'Theater Grid',
        background: const Color(0xFFFFF8F5),
        surface: Colors.white,
        primary: brandPrimary,
        secondary: const Color(0xFFFF8A3D),
        onMedia: Colors.white,
        posterTint: const Color(0xFFFFD9C7),
        radius: 16,
        homeHeadline: 'Free-to-start drama theater',
        dramaHook:
            'Hot list, quick picks, and ready episodes for repeat viewing.',
        walletPitch:
            'Store-safe memberships and tenant-enabled rewards appear here.',
        playerModeLabel: 'Light theater playback',
      ),
    StyleTemplate.douyinInspired => TemplateTokens(
        name: 'Vertical Pulse',
        background: const Color(0xFF050507),
        surface: const Color(0xFF111116),
        primary: brandPrimary,
        secondary: const Color(0xFFFF2D55),
        onMedia: Colors.white,
        posterTint: const Color(0xFF123A46),
        radius: 12,
        homeHeadline: 'Swipe into the next hook',
        dramaHook:
            'Single-column discovery with fast unlock and full-screen motion.',
        walletPitch:
            'Direct-distribution payment options are gated by tenant config.',
        playerModeLabel: 'Full-screen vertical feed',
      ),
    StyleTemplate.hippoInspired => TemplateTokens(
        name: 'Channel Theater',
        background: const Color(0xFFF3FBFA),
        surface: Colors.white,
        primary: brandPrimary,
        secondary: const Color(0xFF0F766E),
        onMedia: const Color(0xFF052F2C),
        posterTint: const Color(0xFFBFEDEA),
        radius: 20,
        homeHeadline: 'Drama channels and VIP lanes',
        dramaHook: 'Category-first browsing with membership clarity.',
        walletPitch:
            'VIP, ad-free, and package entries stay aligned with store rules.',
        playerModeLabel: 'Channel player',
      ),
    StyleTemplate.reelshortInspired => TemplateTokens(
        name: 'Cliffhanger Premium',
        background: const Color(0xFF101010),
        surface: const Color(0xFF1A1715),
        primary: brandPrimary,
        secondary: const Color(0xFFFF5A3D),
        onMedia: Colors.white,
        posterTint: const Color(0xFF4A2B19),
        radius: 14,
        homeHeadline: 'Every episode ends on a cliff',
        dramaHook:
            'Poster-led premium drama with coins and subscription pacing.',
        walletPitch:
            'Coins, trials, and subscriptions follow the selected store mode.',
        playerModeLabel: 'Premium vertical story',
      ),
  };
}
