import 'package:flutter/material.dart';

import '../../app/app_runtime.dart';
import '../../core/api/app_models.dart';
import '../../flavor/flavor.dart';
import '../../theme/template_theme.dart';
import '../../theme/template_visuals.dart';
import '../player/player_screen.dart';

class DramaDetailScreen extends StatefulWidget {
  const DramaDetailScreen({
    required this.flavor,
    required this.dramaId,
    this.drama,
    this.episodes,
    super.key,
  });

  final FlavorConfig flavor;
  final String dramaId;
  final CatalogDrama? drama;
  final List<DramaEpisode>? episodes;

  @override
  State<DramaDetailScreen> createState() => _DramaDetailScreenState();
}

class _DramaDetailScreenState extends State<DramaDetailScreen> {
  Future<DramaDetail>? detailFuture;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    detailFuture ??= AppRuntimeScope.of(context).fetchDrama(widget.dramaId);
  }

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<DramaDetail>(
      future: detailFuture,
      builder: (context, snapshot) {
        final detail = snapshot.data;
        final drama = detail?.drama ?? widget.drama;
        final episodes =
            detail?.episodes ?? widget.episodes ?? _fallbackEpisodes(drama);
        return _DramaDetailBody(
          flavor: widget.flavor,
          dramaId: widget.dramaId,
          drama: drama,
          episodes: episodes.isEmpty ? _fallbackEpisodes(drama) : episodes,
          loading: snapshot.connectionState == ConnectionState.waiting,
          error: snapshot.hasError ? snapshot.error : null,
        );
      },
    );
  }

  List<DramaEpisode> _fallbackEpisodes(CatalogDrama? drama) {
    final episodeCount = drama?.episodeCount ?? 12;
    final safeEpisodeCount = episodeCount < 1 ? 1 : episodeCount;
    return List.generate(
      safeEpisodeCount,
      (index) => DramaEpisode(
        episodeId: index == 0
            ? 'episode_1'
            : '${widget.dramaId}_ep_${(index + 1).toString().padLeft(3, '0')}',
        episodeNumber: index + 1,
        title: 'Episode ${index + 1}',
        pointPrice: drama?.pointPrice ?? 2,
        ready: index < (drama?.readyEpisodeCount ?? 1),
        locked: index > 0,
      ),
    );
  }
}

class _DramaDetailBody extends StatelessWidget {
  const _DramaDetailBody({
    required this.flavor,
    required this.dramaId,
    required this.drama,
    required this.episodes,
    required this.loading,
    required this.error,
  });

  final FlavorConfig flavor;
  final String dramaId;
  final CatalogDrama? drama;
  final List<DramaEpisode> episodes;
  final bool loading;
  final Object? error;

  @override
  Widget build(BuildContext context) {
    final runtime = AppRuntimeScope.of(context);
    final strings = runtime.strings;
    final tokens = templateTokensFor(
      runtime.effectiveCapabilities.styleTemplate,
      runtime.effectiveBrandPrimaryColor,
    );
    final dark = tokens.background.computeLuminance() < 0.25;
    final displayTitle = drama?.title ?? 'Seed Drama';
    final isFavorite = runtime.isFavoriteDrama(dramaId);
    final firstReady = episodes.firstWhere(
      (episode) => episode.ready,
      orElse: () => episodes.first,
    );
    return Scaffold(
      backgroundColor: tokens.background,
      appBar: AppBar(
        backgroundColor: tokens.background,
        foregroundColor: dark ? Colors.white : null,
        title: Text(displayTitle),
      ),
      body: ListView(
        padding: const EdgeInsets.fromLTRB(16, 8, 16, 24),
        children: [
          SizedBox(
            height: 300,
            child: ClipRRect(
              borderRadius: BorderRadius.circular(tokens.radius),
              child: DramaSceneBackdrop(
                tokens: tokens,
                title: displayTitle,
                index: 2,
                child: Padding(
                  padding: const EdgeInsets.all(18),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        children: [
                          Flexible(
                            child: Container(
                              padding: const EdgeInsets.symmetric(
                                horizontal: 10,
                                vertical: 6,
                              ),
                              decoration: BoxDecoration(
                                color: Colors.black.withValues(alpha: 0.38),
                                borderRadius: BorderRadius.circular(999),
                              ),
                              child: Text(
                                templateHeroKicker(tokens),
                                maxLines: 1,
                                overflow: TextOverflow.ellipsis,
                                style: const TextStyle(
                                  color: Colors.white,
                                  fontSize: 12,
                                  fontWeight: FontWeight.w900,
                                ),
                              ),
                            ),
                          ),
                          const Spacer(),
                          Icon(
                            Icons.hd_rounded,
                            color: Colors.white.withValues(alpha: 0.9),
                          ),
                        ],
                      ),
                      const Spacer(),
                      Row(
                        crossAxisAlignment: CrossAxisAlignment.end,
                        children: [
                          SizedBox(
                            width: 98,
                            child: DramaPosterCard(
                              tokens: tokens,
                              title: displayTitle,
                              index: 2,
                              compact: true,
                            ),
                          ),
                          const SizedBox(width: 14),
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              mainAxisSize: MainAxisSize.min,
                              children: [
                                Text(
                                  displayTitle,
                                  maxLines: 2,
                                  overflow: TextOverflow.ellipsis,
                                  style: Theme.of(context)
                                      .textTheme
                                      .headlineSmall
                                      ?.copyWith(
                                        color: Colors.white,
                                        fontWeight: FontWeight.w900,
                                        height: 1.04,
                                      ),
                                ),
                                const SizedBox(height: 8),
                                Text(
                                  templatePrimaryMetric(tokens, drama),
                                  style: TextStyle(
                                    color: Colors.white.withValues(alpha: 0.78),
                                    fontWeight: FontWeight.w700,
                                  ),
                                ),
                              ],
                            ),
                          ),
                        ],
                      ),
                    ],
                  ),
                ),
              ),
            ),
          ),
          const SizedBox(height: 16),
          Text(
            displayTitle,
            style: Theme.of(context).textTheme.headlineSmall?.copyWith(
                  color: dark ? Colors.white : null,
                  fontWeight: FontWeight.w900,
                ),
          ),
          const SizedBox(height: 8),
          Text(
            '${drama?.readyEpisodeCount ?? 1}/${drama?.episodeCount ?? episodes.length} episodes ready. Episode access is checked by Tenant Edge.',
            style: TextStyle(color: dark ? Colors.white70 : Colors.black54),
          ),
          if (loading) ...[
            const SizedBox(height: 10),
            const LinearProgressIndicator(minHeight: 3),
          ],
          if (error != null) ...[
            const SizedBox(height: 10),
            Text(
              'Detail temporarily unavailable. Showing local catalog data.',
              style: TextStyle(color: runtime.effectiveBrandPrimaryColor),
            ),
          ],
          const SizedBox(height: 16),
          Row(
            children: [
              Expanded(
                child: FilledButton.icon(
                  onPressed: () => Navigator.of(context).push(
                    MaterialPageRoute(
                      builder: (_) => PlayerScreen(
                        flavor: flavor,
                        dramaId: dramaId,
                        episodeId: firstReady.episodeId,
                        dramaTitle: displayTitle,
                        episodeTitle: firstReady.title,
                        episodes: episodes,
                      ),
                    ),
                  ),
                  icon: const Icon(Icons.play_arrow_rounded),
                  label: Text(strings.startWatching),
                ),
              ),
              const SizedBox(width: 10),
              IconButton.filledTonal(
                onPressed: () {
                  runtime.toggleFavorite(
                    dramaId: dramaId,
                    title: displayTitle,
                  );
                  ScaffoldMessenger.of(context).showSnackBar(
                    SnackBar(
                      content: Text(
                        isFavorite
                            ? 'Removed from favorites.'
                            : 'Added to favorites.',
                      ),
                    ),
                  );
                },
                icon: Icon(
                  isFavorite
                      ? Icons.favorite_rounded
                      : Icons.favorite_border_rounded,
                ),
              ),
              IconButton.filledTonal(
                onPressed: () {
                  if (!isFavorite) {
                    runtime.toggleFavorite(
                      dramaId: dramaId,
                      title: displayTitle,
                    );
                  }
                  ScaffoldMessenger.of(context).showSnackBar(
                    const SnackBar(
                      content: Text('Saved to your library.'),
                    ),
                  );
                },
                icon: Icon(
                  isFavorite
                      ? Icons.bookmark_rounded
                      : Icons.bookmark_border_rounded,
                ),
              ),
            ],
          ),
          const SizedBox(height: 20),
          Row(
            children: [
              Text(
                'Episodes',
                style: Theme.of(context).textTheme.titleMedium?.copyWith(
                      color: dark ? Colors.white : null,
                      fontWeight: FontWeight.w900,
                    ),
              ),
              const Spacer(),
              Text(
                '${episodes.where((episode) => episode.ready).length} ready',
                style: TextStyle(
                  color: dark ? Colors.white60 : Colors.black45,
                  fontWeight: FontWeight.w800,
                ),
              ),
            ],
          ),
          const SizedBox(height: 10),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              for (final episode in episodes)
                ChoiceChip(
                  label: Text(
                    '${episode.episodeNumber}',
                    style: TextStyle(
                      color: episode.ready
                          ? null
                          : (dark ? Colors.white38 : Colors.black38),
                      fontWeight: FontWeight.w900,
                    ),
                  ),
                  selected: episode.episodeId == firstReady.episodeId,
                  selectedColor: tokens.primary.withValues(alpha: 0.22),
                  backgroundColor:
                      tokens.surface.withValues(alpha: dark ? 0.12 : 1),
                  onSelected: episode.ready
                      ? (_) => Navigator.of(context).push(
                            MaterialPageRoute(
                              builder: (_) => PlayerScreen(
                                flavor: flavor,
                                dramaId: dramaId,
                                episodeId: episode.episodeId,
                                dramaTitle: displayTitle,
                                episodeTitle: episode.title,
                                episodes: episodes,
                              ),
                            ),
                          )
                      : null,
                ),
            ],
          ),
        ],
      ),
    );
  }
}
