import 'package:flutter/material.dart';

import '../../app/app_runtime.dart';
import '../../core/api/app_models.dart';
import '../../flavor/flavor.dart';
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
    final displayTitle = drama?.title ?? 'Seed Drama';
    final firstReady = episodes.firstWhere(
      (episode) => episode.ready,
      orElse: () => episodes.first,
    );
    return Scaffold(
      appBar: AppBar(title: Text(displayTitle)),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Container(
            height: 220,
            decoration: BoxDecoration(
              color: runtime.effectiveBrandPrimaryColor.withValues(alpha: 0.18),
              borderRadius: BorderRadius.circular(18),
            ),
            child: const Center(
              child: Icon(Icons.play_circle_outline, size: 56),
            ),
          ),
          const SizedBox(height: 16),
          Text(displayTitle, style: Theme.of(context).textTheme.headlineSmall),
          const SizedBox(height: 8),
          Text(
            '${drama?.readyEpisodeCount ?? 1}/${drama?.episodeCount ?? episodes.length} episodes ready. Episode access is checked by Tenant Edge.',
          ),
          if (loading) ...[
            const SizedBox(height: 10),
            const LinearProgressIndicator(minHeight: 3),
          ],
          if (error != null) ...[
            const SizedBox(height: 10),
            Text(
              'Detail unavailable, using catalog data. $error',
              style: TextStyle(color: runtime.effectiveBrandPrimaryColor),
            ),
          ],
          const SizedBox(height: 16),
          FilledButton(
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
            child: Text(strings.startWatching),
          ),
          const SizedBox(height: 20),
          Text('Episodes', style: Theme.of(context).textTheme.titleMedium),
          const SizedBox(height: 10),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              for (final episode in episodes)
                ChoiceChip(
                  label: Text('${episode.episodeNumber}'),
                  selected: episode.episodeId == firstReady.episodeId,
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
