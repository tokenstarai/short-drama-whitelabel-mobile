import 'dart:async';

import 'package:flutter/material.dart';

import '../core/api/app_models.dart';
import '../core/api/tenant_adapter_client.dart';
import '../features/auth/auth_screen.dart';
import '../features/catalog/catalog_screen.dart';
import '../features/drama_detail/drama_detail_screen.dart';
import '../features/home/home_screen.dart';
import '../features/player/player_screen.dart';
import '../features/splash/splash_screen.dart';
import '../features/unlock/unlock_sheet.dart';
import '../features/wallet/wallet_screen.dart';
import '../flavor/flavor.dart';
import '../theme/template_theme.dart';
import 'app_runtime.dart';
import 'demo_adapter_transport.dart';

class PreviewApp extends StatefulWidget {
  const PreviewApp({
    required this.flavor,
    required this.screenId,
    this.localeCode,
    super.key,
  });

  final FlavorConfig flavor;
  final String screenId;
  final String? localeCode;

  @override
  State<PreviewApp> createState() => _PreviewAppState();
}

class _PreviewAppState extends State<PreviewApp> {
  late final AppRuntime runtime;

  @override
  void initState() {
    super.initState();
    runtime = AppRuntime(
      flavor: widget.flavor,
      client: TenantAdapterClient(
        baseUri: Uri.parse(widget.flavor.brand.apiAdapterBase),
        transport: DemoAdapterTransport(
          flavor: widget.flavor,
          endUserRef: 'preview-user',
        ),
      ),
      endUserRef: 'preview-user',
      localeCode: widget.localeCode,
      isDemoMode: true,
    );
    unawaited(runtime.bootstrap());
  }

  @override
  void dispose() {
    runtime.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final tokens = templateTokensFor(
      runtime.effectiveCapabilities.styleTemplate,
      runtime.effectiveBrandPrimaryColor,
    );
    final activeScreenId = _activeScreenId;
    return AppRuntimeScope(
      runtime: runtime,
      child: MaterialApp(
        debugShowCheckedModeBanner: false,
        title: '${runtime.appName} $activeScreenId',
        theme: ThemeData(
          colorScheme: ColorScheme.fromSeed(
            seedColor: tokens.primary,
            brightness: tokens.background.computeLuminance() < 0.25
                ? Brightness.dark
                : Brightness.light,
          ),
          useMaterial3: true,
          scaffoldBackgroundColor: tokens.background,
        ),
        home: _previewScreen(activeScreenId),
      ),
    );
  }

  String get _activeScreenId {
    final queryScreen = Uri.base.queryParameters['screen']?.trim();
    if (queryScreen != null && queryScreen.isNotEmpty) {
      return queryScreen;
    }
    return widget.screenId;
  }

  Widget _previewScreen(String screenId) {
    return switch (screenId) {
      'splash' => _SplashPreview(flavor: widget.flavor),
      'auth' => AuthScreen(
          flavor: widget.flavor,
          callbackLinks: const _PreviewOAuthCallbackLinks(),
        ),
      'catalog' => Scaffold(
          body: SafeArea(
            child: CatalogScreen(
              flavor: widget.flavor,
              catalog: runtime.catalog,
            ),
          ),
        ),
      'detail' => DramaDetailScreen(
          flavor: widget.flavor,
          dramaId: 'drama_1',
          drama: _previewDrama,
          episodes: _previewEpisodes,
        ),
      'player' => PlayerScreen(
          flavor: widget.flavor,
          dramaId: 'drama_1',
          episodeId: 'episode_1',
          dramaTitle: _previewDrama.title,
          episodeTitle: _previewEpisodes.first.title,
          episodes: _previewEpisodes,
        ),
      'unlock' => _UnlockPreview(flavor: widget.flavor),
      'wallet' => WalletScreen(flavor: widget.flavor),
      _ => HomeScreen(flavor: widget.flavor),
    };
  }
}

class _SplashPreview extends StatelessWidget {
  const _SplashPreview({required this.flavor});

  final FlavorConfig flavor;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: SafeArea(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            SplashHeader(flavor: flavor),
            const Spacer(),
            const Icon(Icons.play_circle_fill_rounded, size: 88),
            const SizedBox(height: 18),
            Text(
              flavor.brand.appName,
              textAlign: TextAlign.center,
              style: const TextStyle(fontSize: 26, fontWeight: FontWeight.w900),
            ),
            const SizedBox(height: 8),
            const Text(
              'Loading tenant configuration',
              textAlign: TextAlign.center,
            ),
            const Spacer(),
          ],
        ),
      ),
    );
  }
}

class _UnlockPreview extends StatefulWidget {
  const _UnlockPreview({required this.flavor});

  final FlavorConfig flavor;

  @override
  State<_UnlockPreview> createState() => _UnlockPreviewState();
}

class _UnlockPreviewState extends State<_UnlockPreview> {
  bool opened = false;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (opened) {
      return;
    }
    opened = true;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) {
        showUnlockSheet(context, flavor: widget.flavor);
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    return PlayerScreen(
      flavor: widget.flavor,
      dramaId: 'drama_1',
      episodeId: 'episode_2',
      dramaTitle: _previewDrama.title,
      episodeTitle: 'Episode 2',
      episodes: _previewEpisodes,
      enableNativeVideo: false,
    );
  }
}

class _PreviewOAuthCallbackLinks implements OAuthCallbackLinks {
  const _PreviewOAuthCallbackLinks();

  @override
  Future<Uri?> getInitialLink() async => null;

  @override
  Stream<Uri> get uriLinkStream => const Stream.empty();
}

const _previewDrama = CatalogDrama(
  dramaId: 'drama_1',
  title: 'Contract Wife',
  summary:
      'A fake marriage turns into a public fight for power, love, and revenge.',
  posterUrl: 'assets/visuals/poster_01.jpg',
  episodeCount: 68,
  readyEpisodeCount: 24,
  pointPrice: 30,
  language: 'en-US',
  regions: ['US', 'SG', 'TH'],
  tags: ['Romance', 'Revenge', 'Billionaire'],
);

const _previewEpisodes = [
  DramaEpisode(
    episodeId: 'episode_1',
    episodeNumber: 1,
    title: 'The contract begins',
    pointPrice: 0,
    ready: true,
    locked: false,
  ),
  DramaEpisode(
    episodeId: 'episode_2',
    episodeNumber: 2,
    title: 'A hidden witness',
    pointPrice: 2,
    ready: true,
    locked: true,
  ),
  DramaEpisode(
    episodeId: 'episode_3',
    episodeNumber: 3,
    title: 'The boardroom trap',
    pointPrice: 2,
    ready: true,
    locked: true,
  ),
  DramaEpisode(
    episodeId: 'episode_4',
    episodeNumber: 4,
    title: 'The midnight reveal',
    pointPrice: 2,
    ready: true,
    locked: true,
  ),
];
