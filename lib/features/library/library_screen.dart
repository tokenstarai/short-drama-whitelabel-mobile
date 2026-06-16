import 'package:flutter/material.dart';

import '../../app/app_runtime.dart';
import '../../core/api/app_models.dart';
import '../../flavor/flavor.dart';
import '../../theme/template_theme.dart';
import '../drama_detail/drama_detail_screen.dart';
import '../player/player_screen.dart';

enum LibraryScreenMode { watchHistory, favorites }

class LibraryScreen extends StatelessWidget {
  const LibraryScreen({
    required this.flavor,
    required this.mode,
    super.key,
  });

  final FlavorConfig flavor;
  final LibraryScreenMode mode;

  @override
  Widget build(BuildContext context) {
    final runtime = AppRuntimeScope.of(context);
    final strings = runtime.strings;
    final tokens = templateTokensFor(
      runtime.effectiveCapabilities.styleTemplate,
      runtime.effectiveBrandPrimaryColor,
    );
    final title = switch (mode) {
      LibraryScreenMode.watchHistory => strings.watchHistory,
      LibraryScreenMode.favorites => strings.favorites,
    };
    return Scaffold(
      appBar: AppBar(title: Text(title)),
      body: SafeArea(
        child: mode == LibraryScreenMode.watchHistory
            ? _WatchHistoryList(flavor: flavor, tokens: tokens)
            : _FavoritesList(flavor: flavor, tokens: tokens),
      ),
    );
  }
}

class _WatchHistoryList extends StatelessWidget {
  const _WatchHistoryList({required this.flavor, required this.tokens});

  final FlavorConfig flavor;
  final TemplateTokens tokens;

  @override
  Widget build(BuildContext context) {
    final runtime = AppRuntimeScope.of(context);
    final entries = runtime.watchHistory;
    if (entries.isEmpty) {
      return _EmptyLibraryState(
        icon: Icons.history,
        message: runtime.strings.noWatchHistory,
        tokens: tokens,
      );
    }
    return ListView.separated(
      padding: const EdgeInsets.all(16),
      itemCount: entries.length,
      separatorBuilder: (_, __) => const SizedBox(height: 8),
      itemBuilder: (context, index) {
        final entry = entries[index];
        return Card(
          elevation: 0,
          child: ListTile(
            leading: Icon(Icons.play_circle_outline, color: tokens.primary),
            title: Text(entry.dramaTitle),
            subtitle: Text(entry.episodeTitle),
            trailing: const Icon(Icons.chevron_right),
            onTap: () => Navigator.of(context).push(
              MaterialPageRoute(
                builder: (_) => PlayerScreen(
                  flavor: flavor,
                  dramaId: entry.dramaId,
                  episodeId: entry.episodeId,
                  dramaTitle: entry.dramaTitle,
                  episodeTitle: entry.episodeTitle,
                  episodes: [
                    DramaEpisode(
                      episodeId: entry.episodeId,
                      episodeNumber: 1,
                      title: entry.episodeTitle,
                      pointPrice: 0,
                      ready: true,
                      locked: false,
                    ),
                  ],
                ),
              ),
            ),
          ),
        );
      },
    );
  }
}

class _FavoritesList extends StatelessWidget {
  const _FavoritesList({required this.flavor, required this.tokens});

  final FlavorConfig flavor;
  final TemplateTokens tokens;

  @override
  Widget build(BuildContext context) {
    final runtime = AppRuntimeScope.of(context);
    final favorites = runtime.favorites;
    if (favorites.isEmpty) {
      return _EmptyLibraryState(
        icon: Icons.favorite_border,
        message: runtime.strings.noFavorites,
        tokens: tokens,
      );
    }
    return ListView.separated(
      padding: const EdgeInsets.all(16),
      itemCount: favorites.length,
      separatorBuilder: (_, __) => const SizedBox(height: 8),
      itemBuilder: (context, index) {
        final favorite = favorites[index];
        return Card(
          elevation: 0,
          child: ListTile(
            leading: Icon(Icons.favorite, color: tokens.primary),
            title: Text(favorite.title),
            subtitle: Text(favorite.dramaId),
            trailing: const Icon(Icons.chevron_right),
            onTap: () => Navigator.of(context).push(
              MaterialPageRoute(
                builder: (_) => DramaDetailScreen(
                  flavor: flavor,
                  dramaId: favorite.dramaId,
                  drama: _catalogDramaForFavorite(runtime, favorite),
                ),
              ),
            ),
          ),
        );
      },
    );
  }
}

CatalogDrama _catalogDramaForFavorite(
  AppRuntime runtime,
  FavoriteDrama favorite,
) {
  for (final drama in runtime.catalog) {
    if (drama.dramaId == favorite.dramaId) {
      return drama;
    }
  }
  return CatalogDrama(
    dramaId: favorite.dramaId,
    title: favorite.title,
    posterUrl: '',
    episodeCount: 1,
    readyEpisodeCount: 1,
    pointPrice: 0,
  );
}

class _EmptyLibraryState extends StatelessWidget {
  const _EmptyLibraryState({
    required this.icon,
    required this.message,
    required this.tokens,
  });

  final IconData icon;
  final String message;
  final TemplateTokens tokens;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(icon, size: 54, color: tokens.primary),
            const SizedBox(height: 12),
            Text(
              message,
              textAlign: TextAlign.center,
              style: Theme.of(context).textTheme.titleMedium?.copyWith(
                    fontWeight: FontWeight.w800,
                  ),
            ),
          ],
        ),
      ),
    );
  }
}
