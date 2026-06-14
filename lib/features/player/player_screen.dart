import 'package:flutter/material.dart';
import 'package:video_player/video_player.dart';

import '../../app/app_runtime.dart';
import '../../core/api/app_models.dart';
import '../../core/i18n/app_strings.dart';
import '../../flavor/flavor.dart';
import '../../theme/template_theme.dart';
import '../unlock/unlock_sheet.dart';

class PlayerScreen extends StatefulWidget {
  const PlayerScreen({
    required this.flavor,
    required this.dramaId,
    required this.episodeId,
    this.dramaTitle = 'Seed Drama',
    this.episodeTitle = 'Episode 1',
    this.episodes = const [],
    this.enableNativeVideo = true,
    super.key,
  });

  final FlavorConfig flavor;
  final String dramaId;
  final String episodeId;
  final String dramaTitle;
  final String episodeTitle;
  final List<DramaEpisode> episodes;
  final bool enableNativeVideo;

  @override
  State<PlayerScreen> createState() => _PlayerScreenState();
}

class _PlayerScreenState extends State<PlayerScreen> {
  PlayAuthorization? authorization;
  Object? error;
  bool loading = false;
  late String episodeId;
  late String episodeTitle;

  @override
  void initState() {
    super.initState();
    episodeId = widget.episodeId;
    episodeTitle = widget.episodeTitle;
  }

  @override
  void didUpdateWidget(covariant PlayerScreen oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.episodeId != oldWidget.episodeId) {
      episodeId = widget.episodeId;
      episodeTitle = widget.episodeTitle;
      authorization = null;
      error = null;
      loading = false;
    }
  }

  Future<void> authorize() async {
    setState(() {
      loading = true;
      error = null;
    });
    try {
      final runtime = AppRuntimeScope.of(context);
      final result = await runtime.authorizePlayback(
        dramaId: widget.dramaId,
        episodeId: episodeId,
        endUserRef: runtime.endUserRef,
        idempotencyKey:
            'play-${widget.dramaId}-$episodeId-${DateTime.now().millisecondsSinceEpoch}',
      );
      if (!mounted) {
        return;
      }
      runtime.recordPlayback(
        dramaId: widget.dramaId,
        dramaTitle: widget.dramaTitle,
        episodeId: episodeId,
        episodeTitle: episodeTitle,
      );
      setState(() {
        authorization = result;
      });
    } catch (playError) {
      if (!mounted) {
        return;
      }
      setState(() {
        error = playError;
      });
    } finally {
      if (mounted) {
        setState(() {
          loading = false;
        });
      }
    }
  }

  List<DramaEpisode> get readyEpisodes {
    return widget.episodes.where((episode) => episode.ready).toList();
  }

  int get readyEpisodeIndex {
    return readyEpisodes
        .indexWhere((episode) => episode.episodeId == episodeId);
  }

  bool get canGoPrevious => readyEpisodeIndex > 0;

  bool get canGoNext {
    final index = readyEpisodeIndex;
    return index >= 0 && index < readyEpisodes.length - 1;
  }

  void switchEpisode(int offset) {
    final episodes = readyEpisodes;
    final index = readyEpisodeIndex;
    if (index < 0) {
      return;
    }
    final nextIndex = index + offset;
    if (nextIndex < 0 || nextIndex >= episodes.length) {
      return;
    }
    final nextEpisode = episodes[nextIndex];
    setState(() {
      episodeId = nextEpisode.episodeId;
      episodeTitle = nextEpisode.title;
      authorization = null;
      error = null;
      loading = false;
    });
  }

  @override
  Widget build(BuildContext context) {
    final runtime = AppRuntimeScope.of(context);
    final strings = runtime.strings;
    final tokens = templateTokensFor(
      runtime.effectiveCapabilities.styleTemplate,
      runtime.effectiveBrandPrimaryColor,
    );
    final isFavorite = runtime.isFavoriteDrama(widget.dramaId);
    final title = '${widget.dramaTitle} · $episodeTitle';
    return Scaffold(
      backgroundColor: tokens.background.computeLuminance() < 0.25
          ? Colors.black
          : tokens.background,
      body: SafeArea(
        child: Stack(
          children: [
            Positioned.fill(
              child: DecoratedBox(
                decoration: BoxDecoration(
                  gradient: LinearGradient(
                    begin: Alignment.topCenter,
                    end: Alignment.bottomCenter,
                    colors: [
                      tokens.posterTint,
                      tokens.primary.withValues(alpha: 0.78),
                      Colors.black,
                    ],
                  ),
                ),
                child: Center(
                  child: authorization == null
                      ? Icon(
                          Icons.play_circle_fill_rounded,
                          size: 84,
                          color: tokens.onMedia.withValues(alpha: 0.78),
                        )
                      : _AuthorizedVideoView(
                          authorization: authorization!,
                          enableNativeVideo: widget.enableNativeVideo,
                          strings: strings,
                          tokens: tokens,
                        ),
                ),
              ),
            ),
            Positioned(
              top: 8,
              left: 8,
              child: IconButton(
                onPressed: () => Navigator.of(context).pop(),
                icon: const Icon(Icons.arrow_back, color: Colors.white),
              ),
            ),
            Positioned(
              right: 12,
              bottom: 120,
              child: Column(
                children: [
                  IconButton(
                    tooltip: strings.favorites,
                    onPressed: () => runtime.toggleFavorite(
                      dramaId: widget.dramaId,
                      title: widget.dramaTitle,
                    ),
                    icon: Icon(
                      isFavorite ? Icons.favorite : Icons.favorite_border,
                      color: Colors.white,
                    ),
                  ),
                  const SizedBox(height: 18),
                  const Icon(Icons.share_outlined, color: Colors.white),
                  const SizedBox(height: 18),
                  const Icon(Icons.list_alt, color: Colors.white),
                  const SizedBox(height: 18),
                  Text(
                    tokens.name == 'Vertical Pulse'
                        ? strings.swipe
                        : strings.list,
                    style: const TextStyle(color: Colors.white70, fontSize: 12),
                  ),
                ],
              ),
            ),
            Positioned(
              left: 16,
              right: 16,
              bottom: 24,
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    tokens.playerModeLabel,
                    style: const TextStyle(
                      color: Colors.white70,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                  const SizedBox(height: 6),
                  Text(
                    title,
                    style: const TextStyle(
                      color: Colors.white,
                      fontSize: 18,
                      fontWeight: FontWeight.w800,
                    ),
                  ),
                  if (authorization != null) ...[
                    const SizedBox(height: 6),
                    Text(
                      'Grant ${authorization!.grantId} · ${authorization!.manifestHost}',
                      style: const TextStyle(
                        color: Colors.white70,
                        fontSize: 12,
                      ),
                    ),
                  ],
                  if (error != null) ...[
                    const SizedBox(height: 6),
                    Text(
                      '$error',
                      style: const TextStyle(
                        color: Colors.white70,
                        fontSize: 12,
                      ),
                    ),
                  ],
                  const SizedBox(height: 8),
                  Row(
                    children: [
                      Expanded(
                        child: OutlinedButton.icon(
                          onPressed:
                              canGoPrevious ? () => switchEpisode(-1) : null,
                          icon: const Icon(Icons.skip_previous_outlined),
                          label: Text(strings.previousEpisode),
                        ),
                      ),
                      const SizedBox(width: 10),
                      Expanded(
                        child: OutlinedButton.icon(
                          onPressed: canGoNext ? () => switchEpisode(1) : null,
                          icon: const Icon(Icons.skip_next_outlined),
                          label: Text(strings.nextEpisode),
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 8),
                  FilledButton(
                    onPressed: loading ? null : authorize,
                    child: Text(
                      loading ? strings.authorizing : strings.unlockAndPlay,
                    ),
                  ),
                  TextButton(
                    onPressed: () =>
                        showUnlockSheet(context, flavor: widget.flavor),
                    child: Text(
                      strings.moreUnlockOptions,
                      style: const TextStyle(color: Colors.white),
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _AuthorizedVideoView extends StatefulWidget {
  const _AuthorizedVideoView({
    required this.authorization,
    required this.enableNativeVideo,
    required this.strings,
    required this.tokens,
  });

  final PlayAuthorization authorization;
  final bool enableNativeVideo;
  final AppStrings strings;
  final TemplateTokens tokens;

  @override
  State<_AuthorizedVideoView> createState() => _AuthorizedVideoViewState();
}

class _AuthorizedVideoViewState extends State<_AuthorizedVideoView> {
  VideoPlayerController? controller;
  Future<void>? initializeFuture;

  @override
  void initState() {
    super.initState();
    if (widget.enableNativeVideo) {
      createController();
    }
  }

  @override
  void didUpdateWidget(covariant _AuthorizedVideoView oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.authorization.playerUrl != oldWidget.authorization.playerUrl ||
        widget.enableNativeVideo != oldWidget.enableNativeVideo) {
      disposeController();
      if (widget.enableNativeVideo) {
        createController();
      }
    }
  }

  @override
  void dispose() {
    disposeController();
    super.dispose();
  }

  void createController() {
    final uri = Uri.tryParse(widget.authorization.playerUrl);
    if (uri == null || !uri.hasScheme) {
      initializeFuture = Future<void>.error(
        FormatException(
            'Unsupported playback URL', widget.authorization.playerUrl),
      );
      return;
    }
    final nextController = VideoPlayerController.networkUrl(uri);
    controller = nextController;
    initializeFuture = nextController.initialize().then((_) async {
      await nextController.setLooping(false);
      await nextController.play();
    });
  }

  void disposeController() {
    final oldController = controller;
    controller = null;
    initializeFuture = null;
    oldController?.dispose();
  }

  @override
  Widget build(BuildContext context) {
    if (!widget.enableNativeVideo) {
      return _PlaybackFallback(
        authorization: widget.authorization,
        strings: widget.strings,
        tokens: widget.tokens,
      );
    }
    final currentController = controller;
    final currentFuture = initializeFuture;
    if (currentController == null || currentFuture == null) {
      return _PlaybackFallback(
        authorization: widget.authorization,
        strings: widget.strings,
        tokens: widget.tokens,
      );
    }
    return FutureBuilder<void>(
      future: currentFuture,
      builder: (context, snapshot) {
        if (snapshot.hasError) {
          return _PlaybackFallback(
            authorization: widget.authorization,
            strings: widget.strings,
            tokens: widget.tokens,
          );
        }
        if (snapshot.connectionState != ConnectionState.done) {
          return Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              CircularProgressIndicator(color: widget.tokens.onMedia),
              const SizedBox(height: 12),
              Text(
                widget.strings.preparingVideo,
                style: TextStyle(
                  color: widget.tokens.onMedia,
                  fontWeight: FontWeight.w800,
                ),
              ),
            ],
          );
        }
        return Padding(
          padding: const EdgeInsets.symmetric(horizontal: 24),
          child: ClipRRect(
            borderRadius: BorderRadius.circular(widget.tokens.radius),
            child: AspectRatio(
              aspectRatio: currentController.value.aspectRatio == 0
                  ? 9 / 16
                  : currentController.value.aspectRatio,
              child: Stack(
                fit: StackFit.expand,
                children: [
                  VideoPlayer(currentController),
                  Positioned(
                    left: 8,
                    bottom: 8,
                    child: ValueListenableBuilder<VideoPlayerValue>(
                      valueListenable: currentController,
                      builder: (context, value, _) {
                        return IconButton.filled(
                          onPressed: () {
                            value.isPlaying
                                ? currentController.pause()
                                : currentController.play();
                          },
                          icon: Icon(
                            value.isPlaying ? Icons.pause : Icons.play_arrow,
                          ),
                        );
                      },
                    ),
                  ),
                ],
              ),
            ),
          ),
        );
      },
    );
  }
}

class _PlaybackFallback extends StatelessWidget {
  const _PlaybackFallback({
    required this.authorization,
    required this.strings,
    required this.tokens,
  });

  final PlayAuthorization authorization;
  final AppStrings strings;
  final TemplateTokens tokens;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.all(24),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(Icons.verified_rounded, size: 72, color: tokens.onMedia),
          const SizedBox(height: 12),
          Text(
            strings.authorizedPlayer,
            style: TextStyle(
              color: tokens.onMedia,
              fontWeight: FontWeight.w800,
              fontSize: 18,
            ),
          ),
          const SizedBox(height: 8),
          Text(
            strings.playbackFallback,
            textAlign: TextAlign.center,
            style: TextStyle(color: tokens.onMedia.withValues(alpha: 0.72)),
          ),
          const SizedBox(height: 8),
          SelectableText(
            authorization.playerUrl,
            textAlign: TextAlign.center,
            style: TextStyle(
              color: tokens.onMedia.withValues(alpha: 0.72),
              fontSize: 12,
            ),
          ),
        ],
      ),
    );
  }
}
