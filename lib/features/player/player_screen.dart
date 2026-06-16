import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:video_player/video_player.dart';

import '../../app/app_runtime.dart';
import '../../core/api/app_models.dart';
import '../../core/i18n/app_strings.dart';
import '../../flavor/flavor.dart';
import '../../theme/template_theme.dart';
import '../../theme/template_visuals.dart';
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
  final playIdempotencyKeys = <String, String>{};

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
      final targetEpisodeId = episodeId;
      final idempotencyKey = playIdempotencyKeyFor(targetEpisodeId);
      var result = await runtime.authorizePlayback(
        dramaId: widget.dramaId,
        episodeId: targetEpisodeId,
        endUserRef: runtime.endUserRef,
        idempotencyKey: idempotencyKey,
      );
      if (playbackTokenNeedsRefresh(result)) {
        result = await runtime.authorizePlayback(
          dramaId: widget.dramaId,
          episodeId: targetEpisodeId,
          endUserRef: runtime.endUserRef,
          idempotencyKey: idempotencyKey,
        );
        if (playbackTokenNeedsRefresh(result)) {
          throw const AppApiException(
            code: 'APP_PLAYBACK_TOKEN_FAILED',
            message: 'Playback token expired after refresh.',
            requestId: 'local_playback_refresh',
          );
        }
      }
      if (!mounted) {
        return;
      }
      runtime.recordPlayback(
        dramaId: widget.dramaId,
        dramaTitle: widget.dramaTitle,
        episodeId: targetEpisodeId,
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

  String playIdempotencyKeyFor(String targetEpisodeId) {
    final key = '${widget.dramaId}/$targetEpisodeId';
    return playIdempotencyKeys.putIfAbsent(
      key,
      () => 'play-${widget.dramaId}-$targetEpisodeId-'
          '${DateTime.now().millisecondsSinceEpoch}',
    );
  }

  List<DramaEpisode> get readyEpisodes {
    return widget.episodes.where((episode) => episode.ready).toList();
  }

  int get readyEpisodeIndex {
    return readyEpisodes
        .indexWhere((episode) => episode.episodeId == episodeId);
  }

  String get shareLink {
    return '${widget.flavor.deepLinkScheme}://dramas/'
        '${Uri.encodeComponent(widget.dramaId)}/episodes/'
        '${Uri.encodeComponent(episodeId)}';
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
    selectEpisode(nextEpisode);
  }

  void selectEpisode(DramaEpisode nextEpisode) {
    setState(() {
      episodeId = nextEpisode.episodeId;
      episodeTitle = nextEpisode.title;
      authorization = null;
      error = null;
      loading = false;
    });
  }

  Future<void> showEpisodeList(AppStrings strings, TemplateTokens tokens) {
    final episodes = readyEpisodes;
    return showModalBottomSheet<void>(
      context: context,
      showDragHandle: true,
      builder: (sheetContext) {
        return SafeArea(
          child: ListView.separated(
            shrinkWrap: true,
            padding: const EdgeInsets.fromLTRB(16, 0, 16, 18),
            itemCount: episodes.length + 1,
            separatorBuilder: (_, __) => const SizedBox(height: 8),
            itemBuilder: (context, index) {
              if (index == 0) {
                return Padding(
                  padding: const EdgeInsets.only(bottom: 4),
                  child: Text(
                    strings.episodeList,
                    style: Theme.of(context).textTheme.titleLarge?.copyWith(
                          fontWeight: FontWeight.w900,
                        ),
                  ),
                );
              }
              final episode = episodes[index - 1];
              final selected = episode.episodeId == episodeId;
              return ListTile(
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(tokens.radius),
                  side: BorderSide(
                    color: selected
                        ? tokens.primary
                        : tokens.primary.withValues(alpha: 0.14),
                  ),
                ),
                leading: Icon(
                  selected
                      ? Icons.play_circle_fill_rounded
                      : Icons.play_circle_outline,
                  color: tokens.primary,
                ),
                title: Text(episode.title),
                subtitle: Text(strings.episodeCostPoints(episode.pointPrice)),
                trailing: selected ? const Icon(Icons.check_rounded) : null,
                onTap: () {
                  Navigator.of(sheetContext).pop();
                  if (!selected) {
                    selectEpisode(episode);
                  }
                },
              );
            },
          ),
        );
      },
    );
  }

  Future<void> showShareSheet(AppStrings strings, TemplateTokens tokens) {
    final link = shareLink;
    return showModalBottomSheet<void>(
      context: context,
      showDragHandle: true,
      builder: (sheetContext) {
        return SafeArea(
          child: Padding(
            padding: const EdgeInsets.fromLTRB(16, 0, 16, 18),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  strings.shareDrama,
                  style: Theme.of(sheetContext).textTheme.titleLarge?.copyWith(
                        fontWeight: FontWeight.w900,
                      ),
                ),
                const SizedBox(height: 12),
                Text(
                  widget.dramaTitle,
                  style: Theme.of(sheetContext).textTheme.titleMedium?.copyWith(
                        fontWeight: FontWeight.w800,
                      ),
                ),
                const SizedBox(height: 4),
                Text(
                  episodeTitle,
                  style: Theme.of(sheetContext).textTheme.bodyMedium,
                ),
                const SizedBox(height: 14),
                Text(
                  strings.tenantSafeShareLink,
                  style: Theme.of(sheetContext).textTheme.labelLarge?.copyWith(
                        color: tokens.primary,
                        fontWeight: FontWeight.w800,
                      ),
                ),
                const SizedBox(height: 6),
                Container(
                  width: double.infinity,
                  padding: const EdgeInsets.all(12),
                  decoration: BoxDecoration(
                    color: tokens.primary.withValues(alpha: 0.08),
                    borderRadius: BorderRadius.circular(tokens.radius),
                    border: Border.all(
                      color: tokens.primary.withValues(alpha: 0.18),
                    ),
                  ),
                  child: SelectableText(
                    link,
                    style: Theme.of(sheetContext).textTheme.bodyMedium,
                  ),
                ),
                const SizedBox(height: 14),
                SizedBox(
                  width: double.infinity,
                  child: FilledButton.icon(
                    onPressed: () async {
                      await Clipboard.setData(ClipboardData(text: link));
                      if (!mounted) {
                        return;
                      }
                      ScaffoldMessenger.of(context).showSnackBar(
                        SnackBar(content: Text(strings.shareLinkCopied)),
                      );
                    },
                    icon: const Icon(Icons.copy_rounded),
                    label: Text(strings.copyLink),
                  ),
                ),
              ],
            ),
          ),
        );
      },
    );
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
              child: DramaSceneBackdrop(
                tokens: tokens,
                title: widget.dramaTitle,
                index: 3,
                child: Center(
                  child: authorization == null
                      ? _PreAuthorizationVideoOverlay(
                          tokens: tokens,
                          dramaTitle: widget.dramaTitle,
                          episodeTitle: episodeTitle,
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
                  _PlayerActionButton(
                    tooltip: strings.favorites,
                    onPressed: () => runtime.toggleFavorite(
                      dramaId: widget.dramaId,
                      title: widget.dramaTitle,
                    ),
                    icon: Icon(
                      isFavorite ? Icons.favorite : Icons.favorite_border,
                    ),
                    label: '12.8k',
                  ),
                  const SizedBox(height: 18),
                  _PlayerActionButton(
                    tooltip: strings.shareDrama,
                    onPressed: () => showShareSheet(strings, tokens),
                    icon: const Icon(Icons.share_outlined),
                    label: 'Share',
                  ),
                  const SizedBox(height: 18),
                  _PlayerActionButton(
                    tooltip: strings.episodeList,
                    onPressed: readyEpisodes.isEmpty
                        ? null
                        : () => showEpisodeList(strings, tokens),
                    icon: const Icon(Icons.list_alt),
                    label: '${readyEpisodes.length}',
                  ),
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
                      playbackErrorMessage(strings, error),
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
                          style: OutlinedButton.styleFrom(
                            foregroundColor: Colors.white,
                            side: BorderSide(
                              color: Colors.white.withValues(alpha: 0.3),
                            ),
                            backgroundColor:
                                Colors.black.withValues(alpha: 0.18),
                          ),
                          onPressed:
                              canGoPrevious ? () => switchEpisode(-1) : null,
                          icon: const Icon(Icons.skip_previous_outlined),
                          label: Text(strings.previousEpisode),
                        ),
                      ),
                      const SizedBox(width: 10),
                      Expanded(
                        child: OutlinedButton.icon(
                          style: OutlinedButton.styleFrom(
                            foregroundColor: Colors.white,
                            side: BorderSide(
                              color: Colors.white.withValues(alpha: 0.3),
                            ),
                            backgroundColor:
                                Colors.black.withValues(alpha: 0.18),
                          ),
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

class _PreAuthorizationVideoOverlay extends StatelessWidget {
  const _PreAuthorizationVideoOverlay({
    required this.tokens,
    required this.dramaTitle,
    required this.episodeTitle,
  });

  final TemplateTokens tokens;
  final String dramaTitle;
  final String episodeTitle;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 40),
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Container(
            width: 88,
            height: 88,
            decoration: BoxDecoration(
              color: Colors.black.withValues(alpha: 0.34),
              shape: BoxShape.circle,
              border: Border.all(color: Colors.white.withValues(alpha: 0.28)),
            ),
            child: const Icon(
              Icons.play_arrow_rounded,
              color: Colors.white,
              size: 56,
            ),
          ),
          const SizedBox(height: 22),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
            decoration: BoxDecoration(
              color: Colors.black.withValues(alpha: 0.32),
              borderRadius: BorderRadius.circular(999),
            ),
            child: Text(
              '${tokens.playerModeLabel} · $episodeTitle',
              textAlign: TextAlign.center,
              style: const TextStyle(
                color: Colors.white,
                fontWeight: FontWeight.w900,
                fontSize: 12,
              ),
            ),
          ),
          const SizedBox(height: 10),
          Text(
            dramaTitle,
            textAlign: TextAlign.center,
            maxLines: 2,
            overflow: TextOverflow.ellipsis,
            style: Theme.of(context).textTheme.headlineSmall?.copyWith(
                  color: Colors.white,
                  fontWeight: FontWeight.w900,
                  height: 1.05,
                ),
          ),
        ],
      ),
    );
  }
}

class _PlayerActionButton extends StatelessWidget {
  const _PlayerActionButton({
    required this.tooltip,
    required this.onPressed,
    required this.icon,
    required this.label,
  });

  final String tooltip;
  final VoidCallback? onPressed;
  final Widget icon;
  final String label;

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        IconButton.filled(
          tooltip: tooltip,
          onPressed: onPressed,
          style: IconButton.styleFrom(
            backgroundColor: Colors.black.withValues(alpha: 0.34),
            foregroundColor: Colors.white,
          ),
          icon: icon,
        ),
        const SizedBox(height: 4),
        Text(
          label,
          style: const TextStyle(
            color: Colors.white,
            fontSize: 11,
            fontWeight: FontWeight.w800,
          ),
        ),
      ],
    );
  }
}

String playbackErrorMessage(AppStrings strings, Object? error) {
  if (error is AppApiException) {
    return switch (error.code) {
      'APP_INSUFFICIENT_BALANCE' => strings.insufficientBalance,
      'APP_EPISODE_NOT_READY' => strings.episodeNotReady,
      'APP_NOT_FOUND' ||
      'APP_DRAMA_NOT_AVAILABLE' ||
      'APP_FEATURE_DISABLED' =>
        strings.notAuthorized,
      'APP_PLAYBACK_TOKEN_FAILED' => strings.playbackTokenFailed,
      _ => strings.serviceMaintenance,
    };
  }
  return strings.serviceMaintenance;
}

bool playbackTokenNeedsRefresh(
  PlayAuthorization authorization, {
  DateTime? now,
  Duration refreshBefore = const Duration(seconds: 30),
}) {
  final expiresAt = DateTime.tryParse(authorization.tokenExpiresAt);
  if (expiresAt == null) {
    return true;
  }
  final threshold = (now ?? DateTime.now().toUtc()).add(refreshBefore);
  return !expiresAt.toUtc().isAfter(threshold);
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
